"""Observable failed generation attempts through real API, DB and adapter."""
import json
import time
from stack_smoke import request,upload,wait
from pathlib import Path

def terminal(job):
    for _ in range(360):
        run=request('/api/runs/'+job['id'])
        if run['status'] in ('completed','failed'):return run
        time.sleep(.5)
    raise AssertionError('Job deadline')

def main():
    assert request('/api/health')['ai_provider_mode']=='contract-test'
    results=[]
    for marker in ('CONTRACT_BAD_SCHEMA','CONTRACT_BROKEN_TEST','CONTRACT_WRONG_PATCH'):
        pid=request('/api/projects',{'name':'AI negative contract · '+marker})['id']
        upload(pid,'calc.py','def add(a,b): return a-b\n# '+marker)
        upload(pid,'requirements.md','R1. Функция add возвращает сумму a и b. '+marker)
        job=terminal(request(f'/api/projects/{pid}/analyze',{}))
        if marker=='CONTRACT_WRONG_PATCH':
            assert job['status']=='completed'
            run=wait(request(f'/api/projects/{pid}/runs',{}))
            bug=request('/api/bugs?project_id='+pid)[0]
            wait(request(f"/api/bugs/{bug['id']}/confirm-proof",{'confirm_expectation':True,'reviewer_note':'Synthetic negative fixture: 2 + 3 = 5 соответствует R1; проверен неизменный исходный тест.',
                          'run_id':run['id'],'test_sha256':bug['test_sha256']}))
            job=terminal(request(f"/api/bugs/{bug['id']}/propose-fix",{}))
            assert request(f'/api/projects/{pid}/fixes')==[]
        else:
            assert request(f'/api/projects/{pid}/requirements')==[]
            assert request(f'/api/projects/{pid}/test-cases')==[]
        assert job['status']=='failed' and 'invalid_structured_response' in job['error'],job
        stats=request(f'/api/projects/{pid}/ai-statistics')
        assert stats['failed']==2,stats
        results.append({'marker':marker,'project_id':pid,'status':job['status'],'error':job['error'],'ai_statistics':stats})
    Path('work').mkdir(exist_ok=True)
    Path('work/ai-negative-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(results),'observed_failed_attempts':sum(r['ai_statistics']['failed'] for r in results)}))

if __name__=='__main__':main()
