"""Uploaded-project Bug Proof and Fix & Verify state machine.

Only requirement review is a human assertion. All execution is delegated to gVisor.
Storage is copy-on-write: multi-file apply commits file pointers atomically.
"""
import ast
import difflib
import hashlib
import json
import os
from pathlib import PurePosixPath
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from apps.api.db import Project, Record, add_record
from services.runner.contracts import SandboxJob, SourceFile
from services.ai.engine import FailureAnalyzer
from services.ai.patches import PatchPlan, generate_patch
from apps.api import sandbox_client

def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def state_hash(db,pid):
    from apps.api.jobs import DATA
    rows=db.scalars(select(Record).where(Record.project_id==pid,Record.kind.in_(['file','test','requirement'])).execution_options(populate_existing=True)).all()
    value=[]
    for row in rows:
        if row.kind=='file':
            data={'name':row.data['name'],'sha256':hashlib.sha256((DATA / row.data['storage']).read_bytes()).hexdigest()}
        elif row.kind=='test':
            data={key:row.data.get(key) for key in ['code','gherkin','requirement_id','framework','title']}
        else:
            data={key:row.data.get(key) for key in ['key','text']}
            data.update({key:row.data[key] for key in ('source','quote') if key in row.data})
        value.append({'id':row.id,'kind':row.kind,'data':data})
    return digest(json.dumps(sorted(value,key=lambda x:x['id']),sort_keys=True,ensure_ascii=False))

def lock_project(db,pid):
    project=db.scalar(select(Project).where(Project.id==pid).with_for_update().execution_options(populate_existing=True))
    if not project:
        raise HTTPException(404,'Проект не найден')
    return project

def current(db,bug):
    original=db.get(Record,bug.data['run_id'])
    expected=original.data.get('project_state_sha256') if original else None
    if not expected or expected!=state_hash(db,bug.project_id):
        raise HTTPException(409,'Исходники, требования или тесты изменились. Нужен новый запуск и новое доказательство.')
    return original

def case_key(case):
    return (str(case.get('test_id','')),case.get('classname',''),case['name'])

def case_map(result):
    if result.get('status')!='completed' or result.get('runtime')!='runsc':
        raise ValueError('gVisor не завершил прогон; подтверждение запрещено')
    cases=result.get('cases',[])
    mapping={case_key(c):c for c in cases}
    if not cases or len(mapping)!=len(cases):
        raise ValueError('Пустой или неоднозначный набор тестов')
    if any(c['status'] in ('error','skipped') for c in cases):
        raise ValueError('Есть ошибки окружения или пропуски; доказательство неполное')
    if any(FailureAnalyzer.classify(c)=='infrastructure' for c in cases):
        raise ValueError('Есть инфраструктурные сбои; доказательство неполное')
    return mapping

def target_key(bug):
    return tuple(bug.data['case_identity'])

def replay_snapshot(original):
    snapshot=SandboxJob.model_validate(original.data['snapshot']).model_dump(mode='json',exclude_none=True)
    snapshot['id']=str(uuid4())
    snapshot['expected_image_id']=original.data['image_id']
    return snapshot

def proof_job(db,job):
    bug=db.get(Record,job.data['bug_id'])
    original=current(db,bug)
    automatic=job.data.get('review',{}).get('review_kind')=='automated_validation'
    if automatic:
        review=job.data['review'];validation=db.get(Record,review.get('validation_id',''))
        test=db.get(Record,bug.data['test_id'])
        if (not validation or validation.project_id!=bug.project_id or validation.data.get('operation')!='autonomous'
            or validation.data.get('validation',{}).get('status')!='validated'
            or validation.data.get('validated_state_sha256')!=state_hash(db,bug.project_id)
            or not test or test.data.get('validation_id')!=validation.id
            or test.data.get('validation_plan_sha256')!=validation.data['validation']['plan_sha256']
            or review.get('test_sha256')!=digest(test.data['code']) or review.get('run_id')!=original.id):
            raise ValueError('Нет связанной автоматической проверки ожидания')
    result=sandbox_client.execute(replay_snapshot(original))
    # Persist every measurement even if its assessment later rejects the proof.
    job.data={**job.data,'replay':result}
    db.commit()
    before,after=case_map(original.data),case_map(result)
    key=target_key(bug)
    if key not in after or FailureAnalyzer.classify(after[key],True,False)!='reproduced':
        raise ValueError('Исходное assertion-падение не воспроизвелось')
    if {k:c['status'] for k,c in before.items()}!={k:c['status'] for k,c in after.items()}:
        raise ValueError('Повторный прогон отличается от исходного; возможна нестабильность тестов')
    lock_project(db,bug.project_id)
    db.refresh(bug)
    current(db,bug)
    if bug.data['status'] not in ('reproduced','suspected'):
        raise ValueError('Состояние доказательства уже изменилось')
    bug.data={**bug.data,'status':'confirmed','proof_id':job.id,'review':job.data['review'],
              'confirmation_basis':'Evidence-bound automated requirement review and gVisor replay' if automatic else 'Проверка ожидания пользователем по требованию и повторное assertion-падение в чистом gVisor',
              'description':'Автоматически проверенное ожидание и точное повторное падение в gVisor; без ручного подтверждения.' if automatic else 'Ожидание подтверждено пользователем по требованию. Точное падение повторено в gVisor на неизменном снимке, без ошибок окружения.'}
    job.data={**job.data,'status':'completed','assessment':{'reproduced_again':True,'requirement_reviewed':True,'infrastructure_excluded':True,'full_correctness_proven':False}}
    db.commit()

def prepare_patch(snapshot,plan):
    plan=PatchPlan.model_validate(plan)
    source={f['path']:f['content'] for f in snapshot['files']}
    changes=[]
    paths=set()
    changed_lines=0
    for item in plan.changes:
        SourceFile(path=item.path,content=item.content)
        path=PurePosixPath(item.path)
        if item.path in paths or item.path not in source:
            raise ValueError('Патч должен менять только существующие уникальные исходники')
        allowed=('.js','.ts','.tsx','.jsx','.mjs','.cjs') if snapshot.get('profile')=='playwright' else ('.py',)
        if not item.path.endswith(allowed):
            raise ValueError('Патч может менять только реализацию выбранного языка')
        paths.add(item.path)
        if any(p.lower() in ('tests','test','__tests__','node_modules') for p in path.parts) or path.name.startswith('test') or any(marker in path.name for marker in ('.test.','.spec.','.config.')) or path.name.endswith('_test.py') or path.name in ('conftest.py','pytest.py','coverage.py','sitecustomize.py','harness.py','pytest_bootstrap.py'):
            raise ValueError('Изменение тестов или инфраструктуры запрещено')
        before=source[item.path]
        from services.ai.privacy import redact
        if redact(before)[1]:raise ValueError('Изменение источника с обнаруженным секретом запрещено')
        if digest(before)!=item.before_sha256:
            raise ValueError('SHA256 исходника не совпал')
        if before==item.content:
            raise ValueError('Патч не содержит изменения')
        try:
            if not snapshot.get('profile'):ast.parse(item.content)
        except SyntaxError as error:
            raise ValueError('Патч содержит невалидный Python') from error
        # Preserve all source lines in the server-derived unified diff.
        lines=difflib.unified_diff(before.splitlines(True),item.content.splitlines(True),fromfile='a/'+item.path,tofile='b/'+item.path)
        diff=''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in lines)
        changed_lines+=sum(line[:1] in ('+','-') and not line.startswith(('+++','---')) for line in diff.splitlines())
        changes.append({'path':item.path,'before':before,'after':item.content,'before_sha256':digest(before),'after_sha256':digest(item.content),'diff':diff})
    if changed_lines>200:
        raise ValueError('Патч превышает лимит минимального исправления: 200 изменённых строк')
    candidate={**snapshot,'files':[{'path':f['path'],'content':next((c['after'] for c in changes if c['path']==f['path']),f['content'])} for f in snapshot['files']]}
    SandboxJob.model_validate(candidate)
    fingerprint=digest(json.dumps(changes,sort_keys=True,ensure_ascii=False))
    return {'changes':changes,'diff':'\n'.join(c['diff'] for c in changes),'patch_sha256':fingerprint,'explanation':plan.explanation}

def failure_excerpt(trace):
    """Bounded diagnostic, explicitly marked. Stored runner evidence is intact."""
    # Playwright's retry call log repeats observations, often dozens of times.
    # Keep its assertion/locator/expected/received header, not that repetition.
    head=trace.split('Call log:',1)[0].strip()
    if len(head)>1200:head=head[:600]+'\n[diagnostic excerpt]\n'+head[-600:]
    return {'diagnostic_excerpt':head,'full_traceback_chars':len(trace),'excerpted':head!=trace.strip()}

def propose_job(db,job):
    bug=db.get(Record,job.data['bug_id'])
    original=current(db,bug)
    if bug.data['status'] not in ('confirmed','fix_verified') or bug.data.get('proof_id')!=job.data['proof_id']:
        raise ValueError('Требуется актуальное подтверждённое доказательство')
    snapshot=original.data['snapshot']
    submitted=next(t for t in snapshot['tests'] if str(t['id'])==bug.data['test_id'])
    attempt=sum(f.data.get('bug_id')==bug.id for f in db.scalars(select(Record).where(Record.project_id==bug.project_id,Record.kind=='fix')))+1
    context={'operation':'fix','profile':snapshot.get('profile') or 'python-pytest','bug_id':bug.id,'proposal_attempt':attempt,'requirement_key':bug.data['requirement'],'requirement':bug.data['expected'],'expectation_reviewed':True,
             'target_test_id':submitted['id'],'target_case_identity':bug.data['case_identity'],
             'files':[{'path':f['path'],'content':f['content'],'sha256':digest(f['content'])} for f in snapshot['files']]}
    requirements=db.scalars(select(Record).where(Record.project_id==job.project_id,Record.kind=='requirement')).all()
    context['documented_requirements']=[{'key':r.data['key'],'text':r.data['text']} for r in requirements if r.data['key']!=bug.data['requirement']]
    failing_ids={c['test_id'] for c in original.data.get('cases',[]) if c['status']=='failed'}
    context['saved_suite_failures']=[{'test_id':t['id'],'test_sha256':digest(t['code']),'requirement_id':str(t['requirement_id']),
        'cases':[{'name':c['name'],**failure_excerpt(c.get('traceback',''))} for c in original.data['cases'] if c['test_id']==str(t['id']) and c['status']=='failed']}
        for t in snapshot['tests'] if str(t['id']) in failing_ids]
    context['diagnostic_scope']='Frozen case names and assertion excerpts; complete test programs and runner traces are retained server-side and verified unchanged. No inference that a generated assertion is a product requirement.'
    plan=generate_patch(context)
    proposal=prepare_patch(snapshot,plan)
    lock_project(db,bug.project_id)
    db.refresh(bug)
    current(db,bug)
    row=add_record(db,bug.project_id,'fix',{**proposal,'bug_id':bug.id,'proof_id':job.data['proof_id'],
                   'run_id':original.id,'project_state_sha256':original.data['project_state_sha256'],
                   'origin':'llm-contract-test' if os.getenv('LLM_PROVIDER_MODE')=='contract-test' else 'llm',
                   'verified':False,'applied':False,'verification_ids':[]})
    bug.data={**bug.data,'current_fix_id':row.id,'status':'confirmed'}
    job.data={**job.data,'status':'completed','fix_id':row.id}
    db.commit()

def validate_fix(original,fix):
    plan={'explanation':fix.data['explanation'],'changes':[{'path':c['path'],'before_sha256':c['before_sha256'],'content':c['after']} for c in fix.data['changes']]}
    validated=prepare_patch(original.data['snapshot'],plan)
    if validated['patch_sha256']!=fix.data['patch_sha256'] or validated['diff']!=fix.data['diff']:
        raise ValueError('Содержимое или diff предложения изменились')
    return validated

def verify_job(db,job):
    bug=db.get(Record,job.data['bug_id'])
    fix=db.get(Record,job.data['fix_id'])
    original=current(db,bug)
    if fix.data.get('applied') or fix.data['proof_id']!=bug.data.get('proof_id') or job.data['patch_sha256']!=fix.data['patch_sha256']:
        raise ValueError('Предложение устарело или уже применено')
    validated=validate_fix(original,fix)
    baseline_snapshot=replay_snapshot(original)
    baseline=sandbox_client.execute(baseline_snapshot)
    job.data={**job.data,'baseline':baseline}; db.commit()
    before,baseline_cases=case_map(original.data),case_map(baseline)
    key=target_key(bug)
    if key not in baseline_cases or FailureAnalyzer.classify(baseline_cases[key],True,False)!='reproduced' or {k:c['status'] for k,c in before.items()}!={k:c['status'] for k,c in baseline_cases.items()}:
        raise ValueError('Контрольное падение или исходный набор изменились: проверка патча остановлена')
    changes={c['path']:c['after'] for c in validated['changes']}
    candidate={**baseline_snapshot,'id':str(uuid4()),'files':[{'path':f['path'],'content':changes.get(f['path'],f['content'])} for f in baseline_snapshot['files']]}
    focus={**candidate,'id':str(uuid4()),'tests':[t for t in candidate['tests'] if str(t['id'])==bug.data['test_id']]}
    focused=sandbox_client.execute(focus)
    job.data={**job.data,'focused':focused}; db.commit()
    regression=sandbox_client.execute(candidate)
    job.data={**job.data,'regression':regression}; db.commit()
    focused_cases,after=case_map(focused),case_map(regression)
    same_cases=set(before)==set(after)
    original_fixed=key in focused_cases and focused_cases[key]['status']=='passed' and key in after and after[key]['status']=='passed'
    regressions_absent=same_cases and all(after[k]['status']=='passed' for k,c in before.items() if c['status']=='passed')
    all_passed=same_cases and all(c['status']=='passed' for c in after.values())
    assessment={'original_reproduced':True,'original_fixed':original_fixed,'regressions_absent':regressions_absent,
                'same_test_cases':same_cases,'all_regression_passed':all_passed,'tests_unchanged':True,
                'regression_cases_checked':sum(c['status']=='passed' for c in before.values()),
                'total_cases_checked':len(after),'full_correctness_proven':False}
    verified=original_fixed and regressions_absent and all_passed
    lock_project(db,bug.project_id)
    db.refresh(bug); db.refresh(fix)
    current(db,bug)
    if fix.data['patch_sha256']!=job.data['patch_sha256']:
        raise ValueError('Предложение изменилось во время проверки')
    fix.data={**fix.data,'verified':verified,'verification_id':job.id,'assessment':assessment,
              'verification_ids':list(dict.fromkeys([*fix.data.get('verification_ids',[]),job.id]))}
    if bug.data.get('current_fix_id')==fix.id:
        bug.data={**bug.data,'status':'fix_verified' if verified else 'confirmed'}
    job.data={**job.data,**regression,'status':'completed','assessment':assessment,'verified':verified}
    db.commit()

def apply_uploaded(db,bug,fix,approval):
    from apps.api.jobs import DATA
    lock_project(db,bug.project_id)
    db.refresh(bug); db.refresh(fix)
    if not approval.confirm or str(approval.fix_id or '')!=fix.id or str(approval.verification_id or '')!=fix.data.get('verification_id') or approval.patch_sha256!=fix.data['patch_sha256']:
        raise HTTPException(409,'Подтвердите конкретный diff и успешную проверку выбранного предложения')
    if fix.data.get('applied'):
        return fix
    original=current(db,bug)
    verification=db.get(Record,str(approval.verification_id))
    if (not fix.data.get('verified') or not verification or verification.project_id!=bug.project_id
        or verification.data.get('status')!='completed' or verification.data.get('fix_id')!=fix.id
        or not verification.data.get('verified') or verification.data.get('patch_sha256')!=fix.data['patch_sha256']
        or fix.data.get('proof_id')!=bug.data.get('proof_id')):
        raise HTTPException(409,'Нет актуальной успешной проверки этого патча')
    active=db.scalars(select(Record).where(Record.project_id==bug.project_id,Record.kind=='run')).all()
    if any(r.data.get('status') in ('queued','analyzing','generating','running') for r in active):
        raise HTTPException(409,'Дождитесь завершения заданий проекта')
    try:
        validated=validate_fix(original,fix)
    except ValueError as error:
        raise HTTPException(409,str(error)) from error
    rows=db.scalars(select(Record).where(Record.project_id==bug.project_id,Record.kind=='file')).all()
    created=[]
    history=[]
    try:
        for change in validated['changes']:
            matches=[row for row in rows if row.data['name']==change['path']]
            if len(matches)!=1:
                raise HTTPException(409,'Набор исходников изменился')
            row=matches[0]
            before=(DATA / row.data['storage']).read_bytes().decode('utf-8-sig')
            if digest(before)!=change['before_sha256']:
                raise HTTPException(409,'Исходник изменился после проверки')
            storage=str(uuid4())
            path=DATA / storage
            with path.open('xb') as stream:
                created.append(path)
                stream.write(change['after'].encode('utf-8')); stream.flush(); os.fsync(stream.fileno())
            history.append({'file_id':row.id,'path':change['path'],'before_storage':row.data['storage'],'after_storage':storage,
                            'before_sha256':change['before_sha256'],'after_sha256':change['after_sha256']})
            row.data={**row.data,'storage':storage,'size':len(change['after'].encode('utf-8'))}
        fix.data={**fix.data,'applied':True,'application':{'verification_id':verification.id,'patch_sha256':fix.data['patch_sha256'],'files':history,'explicit_user_confirmation':True}}
        db.commit()
        return fix
    except Exception:
        db.rollback()
        # A lost DB acknowledgement can mean commit actually succeeded. Never
        # delete a new blob unless a fresh connection proves it is unreferenced.
        try:
            from apps.api.db import Session
            with Session() as check:
                referenced={row.data['storage'] for row in check.scalars(select(Record).where(Record.kind=='file'))}
            for path in created:
                if path.name not in referenced:
                    path.unlink(missing_ok=True)
        except Exception:
            pass  # Keep harmless orphan blobs rather than risk deleting committed data.
        raise
