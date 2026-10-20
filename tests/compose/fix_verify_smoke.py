"""Real Compose/gVisor workflow. Only external LLM transport is a labelled stub."""
import io
import json
import urllib.error
import urllib.request
import zipfile
from uuid import uuid4
from stack_smoke import request,upload,wait,BASE

def rejected(path,body,status=409):
    try:
        request(path,body,method='POST')
        raise AssertionError('Unsafe transition accepted: '+path)
    except urllib.error.HTTPError as error:
        assert error.code==status,(path,error.code,error.read().decode())

def archive(pid):
    raw=urllib.request.urlopen(BASE+f'/api/projects/{pid}/source-archive').read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return {name:z.read(name) for name in z.namelist()}

def setup(marker=''):
    pid=request('/api/projects',{'name':'Fix & Verify smoke '+marker+' '+uuid4().hex[:6]})['id']
    upload(pid,'calc.py','def add(a,b): return a-b\n')
    upload(pid,'requirements.md','R1. Функция add возвращает сумму a и b. '+marker)
    wait(request(f'/api/projects/{pid}/analyze',{},method='POST'))
    original=wait(request(f'/api/projects/{pid}/runs',{},method='POST'))
    assert original['passed']==2 and original['failed']==1
    bug=request('/api/bugs?project_id='+pid)[0]
    assert bug['status']=='reproduced'
    rejected(f"/api/bugs/{bug['id']}/propose-fix",{})
    review={'confirm_expectation':True,'reviewer_note':'R1 требует математическую сумму: 2 + 3 = 5; assertion проверен человеком.',
            'run_id':original['id'],'test_sha256':bug['test_sha256']}
    rejected(f"/api/bugs/{bug['id']}/confirm-proof",{**review,'confirm_expectation':False})
    rejected(f"/api/bugs/{bug['id']}/confirm-proof",{**review,'test_sha256':'0'*64})
    proof=wait(request(f"/api/bugs/{bug['id']}/confirm-proof",review))
    assert proof['replay']['runtime']=='runsc' and proof['replay']['image_id']==original['image_id']
    assert request('/api/bugs/'+bug['id'])['status']=='confirmed'
    return pid,bug,original

def propose(pid,bug):
    job=wait(request(f"/api/bugs/{bug['id']}/propose-fix",{}))
    fix=next(f for f in request(f'/api/projects/{pid}/fixes') if f['id']==job['fix_id'])
    assert fix['origin']=='llm-contract-test' and fix['patch_sha256']
    return fix

def verify(bug,fix):
    return wait(request(f"/api/bugs/{bug['id']}/verify-fix",{'fix_id':fix['id']}))

def approval(fix,verification):
    return {'confirm':True,'fix_id':fix['id'],'verification_id':verification['id'],'patch_sha256':fix['patch_sha256']}

def main():
    assert request('/api/health')['ai_provider_mode']=='contract-test'
    pid,bug,original=setup()
    before=archive(pid)
    test_codes=[t['code'] for t in request(f'/api/projects/{pid}/test-cases')]
    fix=propose(pid,bug)
    assert '+def add(a,b): return a+b' in fix['diff']
    rejected(f"/api/bugs/{bug['id']}/apply-fix",{'confirm':True,'fix_id':fix['id'],'patch_sha256':fix['patch_sha256']})
    verification=verify(bug,fix)
    assert verification['verified'] and verification['assessment']['tests_unchanged']
    assert verification['assessment']['regression_cases_checked']==2
    assert verification['baseline']['passed']==2 and verification['baseline']['failed']==1
    assert verification['focused']['passed']==1 and verification['focused']['failed']==0
    assert verification['regression']['passed']==3 and verification['regression']['failed']==0
    assert {verification[k]['image_id'] for k in ['baseline','focused','regression']}=={original['image_id']}
    assert archive(pid)==before,'Verification mutated original project'
    body=approval(fix,verification)
    rejected(f"/api/bugs/{bug['id']}/apply-fix",{**body,'confirm':False})
    rejected(f"/api/bugs/{bug['id']}/apply-fix",{**body,'patch_sha256':'0'*64})
    result=request(f"/api/bugs/{bug['id']}/apply-fix",body)
    assert result['applied'] and result['application']['explicit_user_confirmation']
    after=archive(pid)
    assert after['calc.py']==b'def add(a,b): return a+b\n'
    assert after['requirements.md']==before['requirements.md']
    assert [t['code'] for t in request(f'/api/projects/{pid}/test-cases')]==test_codes
    assert request(f"/api/bugs/{bug['id']}/apply-fix",body)['applied'],'Repeated approval is idempotent'
    rerun=wait(request(f'/api/projects/{pid}/runs',{}))
    assert rerun['passed']==3 and rerun['failed']==0

    trap_pid,trap,_=setup('REGRESSION_TRAP')
    trap_before=archive(trap_pid)
    bad=propose(trap_pid,trap)
    bad_run=verify(trap,bad)
    assert not bad_run['verified']
    assert bad_run['assessment']['original_fixed'] and not bad_run['assessment']['regressions_absent']
    rejected(f"/api/bugs/{trap['id']}/apply-fix",approval(bad,bad_run))
    assert archive(trap_pid)==trap_before
    good=propose(trap_pid,trap)
    good_run=verify(trap,good)
    assert good_run['verified'] and len(request(f'/api/projects/{trap_pid}/fixes'))==2
    upload(trap_pid,'extra.py','value = 1\n')
    rejected(f"/api/bugs/{trap['id']}/apply-fix",approval(good,good_run))
    assert archive(trap_pid)['calc.py']==trap_before['calc.py']
    print(json.dumps({'happy_project':pid,'bug_id':bug['id'],'fix_id':fix['id'],'verification_id':verification['id'],
                      'before':{'passed':2,'failed':1},'focused':{'passed':1,'failed':0},'after':{'passed':3,'failed':0},
                      'runtime':'runsc','image_id':original['image_id'],'applied_only_after_confirmation':True,
                      'regression_rejected':True,'stale_source_rejected':True,'test_code_unchanged':True,
                      'llm':'explicit contract-test provider; all executions real'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
