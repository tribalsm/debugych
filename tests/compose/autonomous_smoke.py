"""Offline provider + real API/Celery/Postgres/runsc, including negative gates."""
import json
from pathlib import Path
from stack_smoke import request,upload
from autonomous_benchmark import terminal
from fix_verify_smoke import archive,rejected

def main():
    assert request('/api/health')['ai_provider_mode']=='contract-test'
    rows=[]
    for marker in ('CONTRACT_AUTONOMOUS','CONTRACT_FALSE_REVIEW','CONTRACT_AMBIGUOUS','CONTRACT_BROKEN_TEST'):
        pid=request('/api/projects',{'name':'Autonomous API E2E '+marker})['id']
        upload(pid,'calc.py','def add(a,b): return a-b\n# '+marker+'\n')
        upload(pid,'requirements.md','R1. Функция add возвращает сумму a и b. '+marker)
        before=archive(pid);p=request('/api/projects/'+pid+'/ai-context')
        workflow=terminal(request('/api/projects/'+pid+'/autonomous',{'consent':{'confirm':True,
            'project_state_sha256':p['project_state_sha256'],'provider_fingerprint':p['provider_fingerprint']}}))
        assert before==archive(pid)
        if marker=='CONTRACT_AMBIGUOUS':
            assert workflow['status']=='manual_review_required',workflow
            assert request('/api/projects/'+pid+'/test-cases')==[]
            assert request('/api/bugs?project_id='+pid)==[]
        else:
            assert workflow['status']=='completed' and workflow['verified'],workflow
            assert workflow['qa_report']['autonomous'] and workflow['qa_report']['manual_interventions']==0
            original=request('/api/runs/'+workflow['original_run_id'])
            verification=request('/api/runs/'+workflow['verification_id'])
            assert original['runtime']=='runsc' and original['passed']==2 and original['failed']==1
            assert verification['regression']['passed']==3 and verification['regression']['failed']==0
            if marker=='CONTRACT_FALSE_REVIEW':assert workflow['validation']['classification']=='reviewer_false_rejection'
            if marker=='CONTRACT_BROKEN_TEST':assert workflow['validation']['repairs']==1
            fix=next(f for f in request('/api/projects/'+pid+'/fixes') if f['id']==workflow['fix_id'])
            rejected('/api/bugs/'+workflow['bug_id']+'/apply-fix',{'confirm':False,'fix_id':fix['id'],
                'verification_id':workflow['verification_id'],'patch_sha256':fix['patch_sha256']})
            assert not fix['applied']
        rows.append({'marker':marker,'project_id':pid,'status':workflow['status'],'qa_report':workflow['qa_report'],
            'validation':workflow['validation'],'ai_statistics':request('/api/projects/'+pid+'/ai-statistics')})
    Path('work/autonomous-api-e2e.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(rows),'passed':True,'provider_mode':'contract-test','external_llm_requests':0}))

if __name__=='__main__':main()
