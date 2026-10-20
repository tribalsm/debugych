"""Opt-in QA pipeline. Original files and executed tests are never rewritten."""
from sqlalchemy import select
from apps.api.db import Record,add_record
from services.ai.adapter import AIError
from services.ai.engine import TestGenerator,FailureAnalyzer
from services.ai.validation import LayeredValidator,ManualReview,plan_hash,execution_issue


def process_autonomous(db,job):
    from apps.api import sandbox_client
    from apps.api.jobs import DATA,update,run_uploaded
    from apps.api.uploads import extract_text
    from apps.api.ai_runtime import session
    from apps.api.snapshots import snapshot_project
    from apps.api.bug_workflow import state_hash,proof_job,propose_job,verify_job
    from services.ai.privacy import sanitize_value
    validator=LayeredValidator(sandbox_client.execute)
    source_state=state_hash(db,job.project_id)
    expected_state=source_state
    def stage(name,**data):
        if state_hash(db,job.project_id)!=expected_state:raise AIError('consent_stale_or_missing')
        update(db,job,status='running',stage=name,**data)
    def child(operation,**data):
        row=add_record(db,job.project_id,'run',{'operation':operation,'status':'running','parent_workflow_id':job.id,**data})
        db.commit();return row
    try:
        stage('generation')
        files=db.scalars(select(Record).where(Record.project_id==job.project_id,Record.kind=='file')).all()
        texts=[(f.data['name'],extract_text(f.data['name'],(DATA/f.data['storage']).read_bytes())) for f in files]
        with session(db,job) as adapter:
            adapter.operation_limits={'extract_requirements':1800,'generate_tests':3000,'repair_tests':3000,
                'validate_semantics':1200,'adjudicate_semantics':1400,'generate_patch':1800}
            try:plan=TestGenerator.generate(texts,adapter,validator=validator)
            finally:
                update(db,job,validation=sanitize_value(validator.report),requirement_evidence=getattr(adapter,'requirement_evidence',[]))
            stage('persist_validated_plan')
            if validator.report.get('status')!='validated' or validator.report['plan_sha256']!=plan_hash(plan):raise ManualReview('validation_binding')
            evidence={r['key']:r for r in adapter.requirement_evidence}
            reqs={r.key:add_record(db,job.project_id,'requirement',{**r.model_dump(),**{k:evidence[r.key][k] for k in ('source','quote')}}).id for r in plan.requirements}
            tests=[]
            for index,s in enumerate(plan.scenarios):
                tests.append(add_record(db,job.project_id,'test',{**s.model_dump(),'requirement_id':reqs[s.requirement],
                    'origin':'llm-autonomous-validated','result':'not_run','validation_id':job.id,'scenario_index':index,
                    'validation_plan_sha256':plan_hash(plan)}))
            db.commit()
            expected_state=state_hash(db,job.project_id)
            update(db,job,validated_state_sha256=expected_state,consent_lineage={'uploaded_state':source_state,'validated_state':expected_state,
                'scope':'explicit autonomous QA including test generation, isolated execution, proof, unapplied patch and verification'})
            stage('execution')
            snapshot=snapshot_project(db,job.project_id)
            snapshot['expected_image_id']=validator.report['technical']['image_id']
            original=child('run',snapshot=snapshot,project_state_sha256=expected_state,
                quality_inputs={'requirement_ids':list(reqs.values()),'tests':[{'id':t.id,'requirement_id':t.data['requirement_id'],'dimensions':t.data['dimensions']} for t in tests]})
            run_uploaded(db,original)
            update(db,job,original_run_id=original.id)
            issue=execution_issue(original.data)
            if issue:raise ManualReview(issue)
            discovered=validator.report['technical']['validation']['collected']
            draft_ids=validator.report['technical_test_ids']
            expected={(draft_ids.index(c['test_id']),c['name']) for c in discovered}
            saved_ids=[t.id for t in tests]
            actual={(saved_ids.index(c['test_id']),c['name']) for c in original.data['cases']}
            if expected!=actual or len(expected)!=len(discovered) or len(actual)!=len(original.data['cases']) or any(FailureAnalyzer.classify(c)=='infrastructure' for c in original.data['cases']):raise ManualReview('invalid_test')
            bugs=db.scalars(select(Record).where(Record.project_id==job.project_id,Record.kind=='bug')).all()
            reproduced=[b for b in bugs if b.data.get('run_id')==original.id and b.data['status']=='reproduced']
            if original.data.get('failed') and not reproduced:raise ManualReview('unclassified_failure')
            if reproduced:
                bug=reproduced[0]
                stage('bug_proof')
                proof=child('confirm_proof',bug_id=bug.id,review={'run_id':original.id,'test_sha256':bug.data['test_sha256'],
                    'validation_id':job.id,'review_kind':'automated_validation','reviewer_note':'Evidence-bound semantic validation and independent gVisor syntax/discovery. No human or developer override.'})
                proof_job(db,proof)
                update(db,job,proof_id=proof.id,bug_id=bug.id)
                stage('patch_generation')
                proposal=child('propose_fix',bug_id=bug.id,proof_id=proof.id)
                propose_job(db,proposal)
                fix=db.get(Record,proposal.data['fix_id'])
                stage('fix_verification',fix_id=fix.id)
                verification=child('verify',bug_id=bug.id,fix_id=fix.id,patch_sha256=fix.data['patch_sha256'])
                verify_job(db,verification)
                update(db,job,verification_id=verification.id,verified=verification.data['verified'])
                if not verification.data['verified']:raise ManualReview('patch_or_regression_failure')
            stage('report')
            update(db,job,status='completed',stage='report',qa_report={'autonomous':True,'manual_interventions':0,
                'generated_modules':len(tests),'executed_cases':len(original.data['cases']),
                'passed':original.data['passed'],'assertion_failures':original.data['failed'],'errors':original.data['errors'],
                'findings':len(reproduced),'verified_fix':bool(reproduced),'applied':False,
                'coverage':original.data.get('coverage'),'llm_calls':adapter.calls,
                'reserved_cost_micro_usd':adapter.reserved_micro,'billed_cost_usd':None,
                'limitations':['LLM semantic review is evidence-bound but fallible.','Runner observations are untrusted.','No correctness certificate or patch application.']})
    except Exception as error:
        db.rollback()
        from services.ai.privacy import redact
        kind=error.kind if isinstance(error,ManualReview) else getattr(error,'code','workflow_error')
        if validator.report.get('status')=='pending':validator.report.update(status='failed',classification=kind)
        update(db,job,status='manual_review_required' if isinstance(error,ManualReview) else 'failed',
            error=redact(str(error))[0][:1000],validation=sanitize_value(validator.report),classification=kind,
            qa_report={'autonomous':False,'manual_interventions':0,'stopped_stage':job.data.get('stage'),'classification':kind,'applied':False})
        # Child records must never remain falsely active after a bounded stop.
        for r in db.scalars(select(Record).where(Record.project_id==job.project_id,Record.kind=='run')):
            if r.data.get('parent_workflow_id')==job.id and r.data.get('status')=='running':
                r.data={**r.data,'status':'failed','error':'Parent workflow stopped: '+kind}
        db.commit()
