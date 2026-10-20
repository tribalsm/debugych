"""Independent differential benchmark. Only project folder is ever sent to AI.

Invoke with --allow-external for live transport. No key => explicit NOT VERIFIED.
Private corrections, seed locations and oracle tests are read AFTER generation.
Untrusted code is executed only by the existing runsc supervisor.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from novel_projects import evaluate
from stack_smoke import request
from fix_verify_smoke import archive
from services.ai.quality import compare_variant, identities


def oracle_matches(result, passed, failed):
    cases=result.get('cases',[])
    return (result.get('status')=='completed' and result.get('runtime')=='runsc'
            and len(identities(result))==len(cases)==passed+failed
            and sum(c['status']=='passed' for c in cases)==passed
            and sum(c['status']=='failed' for c in cases)==failed)


def replace(files, changes):
    values={f['path']:f['content'] for f in files}
    for path,before,after in changes:
        if values[path].count(before)!=1:raise ValueError('Private benchmark transform drift')
        values[path]=values[path].replace(before,after)
    return [{'path':p,'content':c} for p,c in values.items()]


def independent(project):
    # This function is called only after AI generation; none of this evaluator
    # data is passed back to AI. Never derive test assertions from these labels.
    name=project['name'];pid=project['project_id']
    frozen=request('/api/runs/'+project['original']['id'])
    if (frozen['project_id']!=pid or frozen.get('project_state_sha256')!=request(f'/api/projects/{pid}/ai-context')['project_state_sha256']):
        raise ValueError('Project changed since generation; benchmark requires frozen source and tests')
    private=json.loads((ROOT/'evaluation/variants.json').read_text(encoding='utf-8'))[name]
    original=[{'path':p,'content':b.decode('utf-8-sig')} for p,b in archive(pid).items() if not p.endswith('.md')]
    reference=replace(original,private['reference'])
    tests=[{k:t[k] for k in ('id','requirement_id','code')} for t in request(f'/api/projects/{pid}/test-cases')]
    python_profile=all(t['framework']=='pytest' for t in request(f'/api/projects/{pid}/test-cases'))
    oracle_code=(ROOT/'evaluation/oracle_tests'/private.get('oracle_test','dispatch_checks.py' if name=='python_dispatch' else 'seat_checks.spec.ts')).read_text(encoding='utf-8')
    oracle=[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':oracle_code}]
    jobs=[]
    def add(label,files,submitted):
        jobs.append({'label':label,'job':{'id':str(uuid4()),'profile':None if python_profile else 'playwright',
            'expected_image_id':project['original']['image_id'],'files':files,'tests':submitted}})
    add('reference',reference,tests)
    for group in ('defects','mutations'):
        for variant in private[group]:
            files=replace(reference,variant['changes'])
            add(variant['id'],files,tests)
            if group=='defects':add('oracle-'+variant['id'],files,oracle)
    add('oracle-original',original,oracle);add('oracle-reference',reference,oracle)
    if project['candidates']:
        fix=next(f for f in request(f'/api/projects/{pid}/fixes') if f['id']==project['candidates'][-1]['fix_id'])
        replacements={c['path']:c['after'] for c in fix['changes']}
        candidate=[{'path':f['path'],'content':replacements.get(f['path'],f['content'])} for f in original]
        add('oracle-candidate',candidate,oracle)
    script='''import json,hashlib
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot
observations=[]
'''
    script+='jobs='+repr(jobs)+'\n'
    script+='''for item in jobs:
    try:
        result=execute_snapshot(SandboxJob.model_validate(item['job']))
        # Artifacts remain in normal API workflow. Never print base64 or secrets.
        result={k:v for k,v in result.items() if k not in ('artifacts','logs')}
        result['tests_sha256']=hashlib.sha256(json.dumps(item['job']['tests'],sort_keys=True).encode()).hexdigest()
    except Exception as error:
        result={'status':'failed','cases':[],'controller_error_type':type(error).__name__}
    observations.append({'label':item['label'],'result':result})
print(json.dumps(observations,ensure_ascii=True),flush=True)
'''
    command=['docker','compose','exec','-T','supervisor','python']
    if os.name=='nt':
        wsl_root='/mnt/'+str(ROOT.drive)[0].lower()+ROOT.as_posix()[2:]
        command=['wsl','-d','Ubuntu','-u','root','--cd',wsl_root,'--',*command]
    completed=subprocess.run(command,input=script.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,timeout=900)
    if completed.returncode:raise RuntimeError('Independent controller failed; no untrusted output logged')
    measured={row['label']:row['result'] for row in json.loads(completed.stdout)}
    baseline=measured['reference']
    # Independently validate the reference and each one-defect variant first.
    oracle_valid=oracle_matches(measured['oracle-reference'],4,0)
    detections=[];mutations=[]
    for group,items in (('defects',detections),('mutations',mutations)):
        for variant in private[group]:
            result=compare_variant(baseline,measured[variant['id']])
            if group=='defects':
                control=measured['oracle-'+variant['id']]
                if not oracle_valid or not oracle_matches(control,3,1):
                    result={**result,'eligible':False,'detected':False,'reason':'private_oracle_control_invalid'}
            items.append({'id':variant['id'],**result})
    original_cases=identities(project['original']);replay=identities(project.get('proof_replay',{}))
    failed=[k for k,c in original_cases.items() if c['status']=='failed']
    proof=project.get('proof_replay',{})
    comparable_replay=(proof.get('status')=='completed' and proof.get('runtime')=='runsc'
        and proof.get('image_id')==project['original']['image_id']
        and original_cases.keys()==replay.keys()
        and all(replay[k]['status']==c['status'] for k,c in original_cases.items()))
    reproduced=len(failed) if comparable_replay else 0
    refcases=list(baseline.get('cases',[]))
    false_reports=sum(c['status']=='failed' for c in refcases)
    eligible=[d for d in detections if d['eligible']]
    mutation_eligible=[d for d in mutations if d['eligible']]
    candidate=measured.get('oracle-candidate')
    return {'oracle_never_sent_to_ai':True,'oracle_reference_valid':oracle_valid,'defects':detections,
        'detected':sum(d['detected'] for d in eligible),'missed':len(detections)-sum(d['detected'] for d in eligible),
        'unassessable':len(detections)-len(eligible),
        'false_reports_on_reference':false_reports if baseline.get('status')=='completed' else None,
        'proof':{'original_assertion_failures':len(failed),'replayed_failures':reproduced,
                 'reproduction_ratio':reproduced/len(failed) if failed and replay else None,
                 'human_review':('automated_validation_no_human' if project.get('autonomous') else 'agent_review_not_human' if project.get('explicit_draft_review',{}).get('draft_review',{}).get('reviewer_kind')=='agent'
                    else 'synthetic fixture only' if project['mode']=='contract-test' else 'recorded_review' if proofs_present(project) else 'pending')},
        'fix':{'generated':len(project['candidates']),'verified':sum(c['verified'] for c in project['candidates']),
               'latest_verified':bool(project['candidates'] and project['candidates'][-1]['verified']),
               'oracle_remaining_failures':candidate.get('failed') if candidate else None,
               'oracle_passed':candidate.get('passed') if candidate else None,
               'regression_absent_in_generated_suite':all(c['assessment']['regressions_absent'] for c in project['candidates']) if candidate else None,
               'applied':False},
        'seeded_mutation':{'results':mutations,'eligible':len(mutation_eligible),'killed':sum(d['detected'] for d in mutation_eligible),
                           'score':sum(d['detected'] for d in mutation_eligible)/len(mutation_eligible) if mutation_eligible else None,
                           'scope':'One hand-seeded mutation per project, not a broad mutation-testing campaign.'},
        'reference_observations':baseline,'isolated_observations':measured}


def proofs_present(project):
    return bool(project.get('proof_replay'))


def resume_project(project):
    """Read an explicitly reviewed proof/fix; never approve or apply it here."""
    project={**project}
    if project.get('name') not in ('python_dispatch','react_booking','parcel_cart_v2','team_invoice_v2'):
        raise ValueError('Only benchmark control projects can be resumed')
    pid=project['project_id'];original_id=project['original']['id']
    runs=request(f'/api/projects/{pid}/runs')
    proofs=[r for r in runs if r['operation']=='confirm_proof' and r['status']=='completed'
            and r.get('review',{}).get('run_id')==original_id]
    if proofs:
        project['proof_replay']=proofs[-1]['replay']
        project['pending_user_review']=False
    project['candidates']=[]
    for fix in request(f'/api/projects/{pid}/fixes'):
        if fix.get('run_id')!=original_id:continue
        project['candidates'].append({'fix_id':fix['id'],'verification_id':fix.get('verification_id'),
            'verified':fix.get('verified',False),'assessment':fix.get('assessment',{'regressions_absent':False})})
    project['ai_statistics']=request(f'/api/projects/{pid}/ai-statistics')
    project['benchmark']=independent(project)
    return project


def main():
    started=time.monotonic()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-external',action='store_true',help='Consent to send ONLY evaluation/projects sources and requirements to configured provider')
    parser.add_argument('--output',default='work/benchmark-results.json')
    parser.add_argument('--project',action='append',choices=('python_dispatch','react_booking'),
                        help='Limit fresh evaluation to selected synthetic project(s); default: both')
    parser.add_argument('--resume-report',help='Re-evaluate projects after manual Bug Proof / Fix & Verify in UI; sends nothing to LLM')
    args=parser.parse_args()
    health=request('/api/health');mode=health['ai_provider_mode']
    report={'provider_mode':mode,'live_llm_verified':False,'results':[]}
    if args.resume_report:
        previous=json.loads(Path(args.resume_report).read_text(encoding='utf-8'))
        if previous.get('provider_mode') not in ('live','contract-test'):
            raise ValueError('Invalid benchmark provider mode')
        report={**previous,'results':[]}
        for project in previous['results']:
            try:report['results'].append(resume_project(project))
            except Exception as error:report['results'].append({'name':project.get('name'),'workflow_error_type':type(error).__name__})
        report['live_llm_verified']=(report['provider_mode']=='live' and len(report['results'])==2 and
            all('benchmark' in p and p['benchmark']['fix'].get('latest_verified')
                and p['benchmark']['fix']['oracle_remaining_failures']==0
                and p['benchmark']['proof']['reproduction_ratio']==1 for p in report['results']))
    elif not health['ai_available']:
        report['status']='NOT_VERIFIED_API_KEY_MISSING'
    else:
        if mode!='contract-test' and not args.allow_external:
            raise SystemExit('Review evaluation/projects first; live benchmark requires explicit --allow-external.')
        if mode!='contract-test':
            import stack_smoke
            stack_smoke.ALLOW_LIVE_TEST_TRANSPORT=True
        report['status']='CONTRACT_INFRASTRUCTURE_ONLY' if mode=='contract-test' else 'LIVE_ATTEMPTED'
        for name in args.project or ('python_dispatch','react_booking'):
            project_started=time.monotonic()
            print('Benchmark: '+name+' ['+mode+']',flush=True)
            try:
                project=evaluate(name,mode)
                project['benchmark']=independent(project)
                project['workflow_seconds']=round(time.monotonic()-project_started,3)
                report['results'].append(project)
                print(json.dumps({'project':name,**{k:project['benchmark'][k] for k in ('detected','missed','unassessable','false_reports_on_reference')} }),flush=True)
            except Exception as error:
                failed={'name':name,'mode':mode,'workflow_error_type':getattr(error,'cause_type',type(error).__name__),
                        'workflow_seconds':round(time.monotonic()-project_started,3)}
                if getattr(error,'project_id',None):
                    failed['project_id']=error.project_id
                    failed['ai_statistics']=request(f'/api/projects/{error.project_id}/ai-statistics')
                    failed['jobs']=[{k:r.get(k) for k in ('id','operation','status')} for r in request(f'/api/projects/{error.project_id}/runs')]
                report['results'].append(failed)
        report['live_generation_execution_verified']=(mode=='live' and len(report['results'])==2 and all('benchmark' in r for r in report['results']))
        # End-to-end live proof/fix verification remains pending human review.
    report['notice']='Contract answers are prepared fixtures; they measure pipeline/evaluator behavior, never autonomous LLM discovery. Live fixes require separate human expectation review.'
    report['evaluation_seconds']=round(time.monotonic()-started,3)
    output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'projects':len(report['results'])}),flush=True)
    if any('workflow_error_type' in r for r in report['results']):raise SystemExit(1)


if __name__=='__main__':main()
