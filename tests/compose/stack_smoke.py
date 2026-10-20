"""Run against Compose + compose.test.yml. All test execution remains real.

LLM is an explicitly stubbed external transport; sources and returned test code
go through the actual API, Postgres, Redis, Celery and gVisor supervisor.
"""
import json
import os
import time
import urllib.request
from uuid import uuid4

BASE=os.getenv('SMOKE_URL','http://127.0.0.1:8080')
ALLOW_LIVE_TEST_TRANSPORT=False

def request(path,data=None,method=None,headers=None):
    # Automated fixtures explicitly approve only their own freshly inspected state.
    # Raw transport is available for negative consent tests.
    if isinstance(data,dict) and not data.get('consent') and (path.endswith('/analyze') or path.endswith('/propose-fix')):
        if request('/api/health')['ai_provider_mode']!='contract-test' and not ALLOW_LIVE_TEST_TRANSPORT:
            raise RuntimeError('Contract test mode required; live evaluator requires explicit --allow-external')
        if path.endswith('/analyze'):pid=path.split('/')[3]
        else:pid=request('/api/bugs/'+path.split('/')[3])['project_id']
        preview=request('/api/projects/'+pid+'/ai-context')
        data={**data,'consent':{'confirm':True,'project_state_sha256':preview['project_state_sha256'],'provider_fingerprint':preview['provider_fingerprint']}}

    if isinstance(data,dict):
        data=json.dumps(data).encode()
        headers={**(headers or {}),'Content-Type':'application/json'}
    req=urllib.request.Request(BASE+path,data=data,headers=headers or {},method=method)
    with urllib.request.urlopen(req,timeout=15) as response:
        return json.load(response)

def upload(pid,name,text):
    boundary='debugych'+uuid4().hex
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/plain\r\n\r\n{text}\r\n--{boundary}--\r\n').encode()
    return request(f'/api/projects/{pid}/files',body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})

def wait(job):
    for _ in range(360):
        value=request('/api/runs/'+job['id'])
        if value['status'] in ('completed','failed'):
            assert value['status']=='completed',value
            return value
        time.sleep(.5)
    raise AssertionError('Job deadline exceeded')

def main():
    assert request('/api/health')['execution']=='gvisor-python'
    pid=request('/api/projects',{'name':'Compose smoke · '+uuid4().hex[:8]})['id']
    upload(pid,'calc.py','def add(a,b): return a-b\n')
    upload(pid,'requirements.md','# Требования\nR1. add возвращает сумму a и b.\n')
    analysis=wait(request(f'/api/projects/{pid}/analyze',{},method='POST'))
    tests=request(f'/api/projects/{pid}/test-cases')
    assert tests[0]['origin']=='llm-contract-test' and 'assert add(2,3)==5' in tests[0]['code']
    result=wait(request(f'/api/projects/{pid}/runs',{},method='POST'))
    assert result['runtime']=='runsc' and result['failed']==1 and result['passed']==2,result
    assert result['coverage']['totals']['percent_covered']>0
    bugs=request('/api/bugs?project_id='+pid)
    assert len(bugs)==1 and bugs[0]['status']=='reproduced',bugs
    assert bugs[0]['requirement_id']==tests[0]['requirement_id']
    assert request(f'/api/projects/{pid}/test-cases')[0]['result']=='failed'
    exported=urllib.request.urlopen(BASE+'/api/exports?project_id='+pid+'&format=py').read().decode()
    assert exported==tests[0]['code']
    print(json.dumps({'project_id':pid,'job_id':result['id'],'runtime':result['runtime'],'passed':result['passed'],'failed':result['failed'],
                      'coverage':result['coverage']['totals'],'snapshot_sha256':result['snapshot_sha256'],'bug_status':bugs[0]['status'],
                      'llm':'stubbed provider transport; real execution'},indent=2))

if __name__=='__main__':main()
