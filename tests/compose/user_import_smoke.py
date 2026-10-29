"""Own uploaded tests -> existing gVisor, no AI generation or patch application."""
import json
import os
import time
import urllib.request
from urllib.parse import urlsplit
from uuid import uuid4

BASE=os.getenv('API_BASE','http://127.0.0.1:8000').rstrip('/')
u=urlsplit(BASE)
if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost') or u.username or u.password or u.path or u.query or u.fragment:
    raise SystemExit('Only an explicit private loopback test API is allowed')
client=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path,body=None,method=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(BASE+path,data=data,method=method,headers={'Content-Type':'application/json'})
    with client.open(req,timeout=15) as reply:return json.load(reply)

def upload(pid,name,content):
    boundary=uuid4().hex
    data=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/plain\r\n\r\n{content}\r\n--{boundary}--\r\n').encode()
    req=urllib.request.Request(BASE+f'/api/projects/{pid}/files',data=data,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    with client.open(req,timeout=15) as reply:assert reply.status==201

def wait(identity):
    for _ in range(120):
        result=request('/api/runs/'+identity)
        if result['status'] not in ('queued','running','analyzing','generating'):return result
        time.sleep(.5)
    raise AssertionError('Execution did not reach a terminal state')

def main():
    assert request('/api/health')['sandbox_available']
    fixtures=[('pytest',2,{
        'calc.py':'def add(a,b): return a+b\n',
        'test_calc.py':'from calc import add\ndef test_add(): assert add(1,2)==3\ndef test_zero(): assert add(-1,1)==0\n',
    }),('playwright',1,{
        'index.html':'<h1>Counter</h1><button>0</button><script type="module" src="/app.js"></script>',
        'app.js':"const b=document.querySelector('button');b.addEventListener('click',()=>{b.textContent=String(Number(b.textContent)+1)})",
        'counter.spec.ts':"import {test,expect} from '@playwright/test';test('counter',async({page})=>{await page.goto('/');await page.getByRole('button').click();await expect(page.getByRole('button')).toHaveText('1')});",
    })]
    results=[]
    for profile,count,files in fixtures:
        pid=request('/api/projects',{'name':'Readiness import smoke '+profile})['id']
        try:
            for name,content in files.items():upload(pid,name,content)
            imported=request(f'/api/projects/{pid}/import-tests',{},'POST')
            assert imported['imported']==1 and imported['tests'][0]['origin']=='uploaded-user-tests'
            job=request(f'/api/projects/{pid}/runs',{},'POST');result=wait(job['id'])
            assert result['status']=='completed',result.get('error')
            assert result['runtime']=='runsc'
            assert result['passed']==count and result['failed']==0 and result['errors']==0
            assert result['coverage']['totals']['num_statements']>0
            assert request(f'/api/projects/{pid}/ai-statistics')['attempts']==0
            if profile=='playwright':assert any(a['media_type']=='image/png' for a in result['artifacts'])
            results.append({'profile':profile,'passed':count,'runtime':result['runtime'],'coverage_kind':result.get('coverage_kind') or 'coverage.py'})
        finally:request('/api/projects/'+pid,method='DELETE')
    print(json.dumps({'uploaded_tests':results,'llm_requests':0,'patch_applications':0}))

if __name__=='__main__':main()
