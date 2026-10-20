"""Contract transport + actual API/Postgres/Celery/gVisor, no live LLM calls."""
import hashlib,json
from pathlib import Path
from stack_smoke import request,upload,wait
from ai_negative_smoke import terminal
from fix_verify_smoke import rejected,archive,verify

def main():
    assert request('/api/health')['ai_provider_mode']=='contract-test'
    pid=request('/api/projects',{'name':'Contract rejected draft review E2E'})['id']
    upload(pid,'calc.py','def add(a,b): return a-b\n')
    upload(pid,'requirements.md','R1. Функция add возвращает сумму a и b.')
    analysis=terminal(request(f'/api/projects/{pid}/analyze',{}))
    assert analysis['status']=='failed' and 'test_review_rejected' in analysis['error'],analysis
    plan=analysis['generation_review']['drafts'][1]['plan']
    body={'confirm':True,'analysis_id':analysis['id'],'draft_index':1,
        'draft_sha256':hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'project_state_sha256':request(f'/api/projects/{pid}/ai-context')['project_state_sha256'],
        'reviewer_kind':'agent','reviewer_note':'Contract fixture agent review: public R1 requires mathematical addition; unchanged generated assertions 2+3=5 and zero cases are correct.'}
    rejected(f'/api/projects/{pid}/accept-ai-draft',{**body,'confirm':False})
    rejected(f'/api/projects/{pid}/accept-ai-draft',{**body,'draft_sha256':'0'*64})
    accepted=request(f'/api/projects/{pid}/accept-ai-draft',body)
    before=archive(pid);codes=[s['code'] for s in plan['scenarios']]
    assert [t['code'] for t in request(f'/api/projects/{pid}/test-cases')]==codes
    run=wait(request(f'/api/projects/{pid}/runs',{}))
    assert run['runtime']=='runsc' and run['passed']==2 and run['failed']==1
    bug=next(b for b in request('/api/bugs?project_id='+pid) if b['status']=='reproduced')
    proof=wait(request(f"/api/bugs/{bug['id']}/confirm-proof",{'confirm_expectation':True,'reviewer_note':body['reviewer_note'],
        'run_id':run['id'],'test_sha256':bug['test_sha256']}))
    proposed=wait(request(f"/api/bugs/{bug['id']}/propose-fix",{}))
    fix=next(f for f in request(f'/api/projects/{pid}/fixes') if f['id']==proposed['fix_id'])
    checked=verify(bug,fix)
    assert checked['verified'] and checked['regression']['passed']==3
    rejected(f"/api/bugs/{bug['id']}/apply-fix",{'confirm':False,'fix_id':fix['id'],
        'verification_id':checked['id'],'patch_sha256':fix['patch_sha256']})
    assert before==archive(pid) and [t['code'] for t in request(f'/api/projects/{pid}/test-cases')]==codes
    assert request('/api/runs/'+analysis['id'])['status']=='failed'
    result={'provider_mode':'contract-test','project_id':pid,'analysis_id':analysis['id'],'acceptance_id':accepted['id'],
        'run_id':run['id'],'proof_id':proof['id'],'verification_id':checked['id'],'verified':True,
        'before':{'passed':2,'failed':1},'after':{'passed':3,'failed':0},'runtime':'runsc',
        'tests_unchanged':True,'source_unchanged':True,'unconfirmed_apply_rejected':True,'applied':False}
    Path('work/draft-review-e2e.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
