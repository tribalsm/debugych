"""Real uploaded JS/TS -> Celery -> Chromium inside gVisor -> stored artifacts."""
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from stack_smoke import BASE,request,upload,wait

ROOT=Path(__file__).resolve().parents[2]

def setup(extension='ts'):
    pid=request('/api/projects',{'name':'Playwright gVisor · '+extension})['id']
    index=(ROOT/'demo/sample-ts-app/index.html').read_text(encoding='utf-8').replace('main.ts','main.'+extension)
    code=(ROOT/'demo/sample-ts-app/main.ts').read_text(encoding='utf-8')
    if extension=='js':code=code.replace(': number','').replace(")!.",").")
    upload(pid,'index.html',index)
    upload(pid,'main.'+extension,code)
    upload(pid,'requirements.md',(ROOT/'demo/sample-ts-app/requirements.md').read_text(encoding='utf-8'))
    # These must never execute. Project config/scripts are data only.
    upload(pid,'package.json',json.dumps({'scripts':{'postinstall':'exit 77','start':'exit 78'},'dependencies':{'unapproved-library':'999.0.0'}}))
    upload(pid,'playwright.config.js',"throw new Error('Uploaded config must not execute');")
    wait(request(f'/api/projects/{pid}/analyze',{}))
    return pid

def artifacts(run):
    values=run['artifacts']
    images=[a for a in values if a['media_type']=='image/png']
    assert len(images)==3,values
    assert {a['name'] for a in values if a['media_type']=='application/json'}=={'playwright-report.json','coverage-istanbul.json'}
    for artifact in values:
        response=urllib.request.urlopen(BASE+f"/api/runs/{run['id']}/artifacts/{artifact['id']}")
        content=response.read()
        assert hashlib.sha256(content).hexdigest()==artifact['sha256']
        assert len(content)==artifact['size']
        assert response.headers['X-Content-Type-Options']=='nosniff'
        if artifact['media_type']=='image/png':assert content.startswith(b'\x89PNG\r\n\x1a\n')
        elif artifact['name']=='playwright-report.json':
            report=json.loads(content)
            assert len(report['cases'])==3 and report['framework']=='playwright'
            assert len(report['browser_observations'])==3
    return len(images)

def main():
    assert request('/api/health')['playwright_available']
    results=[]
    for extension in ('js','ts'):
        pid=setup(extension)
        run=wait(request(f'/api/projects/{pid}/runs',{}))
        assert run['profile']=='playwright' and run['runtime']=='runsc'
        assert run['passed']==2 and run['failed']==1 and not run['errors'],run
        assert run['coverage']['totals']['percent_covered']>0
        assert run['coverage_kind']=='istanbul-original-source'
        assert run['snapshot_sha256'] and run['image_id'].startswith('sha256:')
        count=artifacts(run)
        bugs=request('/api/bugs?project_id='+pid)
        assert len(bugs)==1 and bugs[0]['status']=='reproduced' and bugs[0]['framework']=='playwright',bugs
        # Browser assertion, not a timeout or environment failure, can be reviewed/replayed.
        bug=bugs[0]
        proof=wait(request(f"/api/bugs/{bug['id']}/confirm-proof",{'confirm_expectation':True,'reviewer_note':'R1 явно требует увеличение нулевого значения на один, проверка toHaveText соответствует требованию.',
                       'run_id':run['id'],'test_sha256':bug['test_sha256']}))
        assert proof['replay']['image_id']==run['image_id']
        assert request('/api/bugs/'+bug['id'])['status']=='confirmed'
        # Editing generated TS with broken syntax is an environment failure, no new finding.
        test=request(f'/api/projects/{pid}/test-cases')[0]
        request('/api/test-cases/'+test['id'],{k:('const broken: =' if k=='code' else test[k]) for k in ('title','gherkin','code')},method='PATCH')
        bad=request(f'/api/projects/{pid}/runs',{})
        for _ in range(120):
            bad=request('/api/runs/'+bad['id'])
            if bad['status'] in ('completed','failed'):break
            time.sleep(.5)
        assert bad['status']=='failed' and not bad.get('passed'),bad
        assert len(request('/api/bugs?project_id='+pid))==1
        runtime_code="import {test,expect} from '@playwright/test'; test('runtime error',async({page})=>{await page.goto('/');await page.evaluate(()=>setTimeout(()=>{throw new Error('browser runtime probe')},0));await page.waitForTimeout(100);expect(true).toBe(true);});"
        request('/api/test-cases/'+test['id'],{k:(runtime_code if k=='code' else test[k]) for k in ('title','gherkin','code')},method='PATCH')
        runtime=wait(request(f'/api/projects/{pid}/runs',{}))
        assert runtime['errors']==1 and runtime['passed']==0,runtime
        assert len(request('/api/bugs?project_id='+pid))==1
        # Old measured artifacts remain downloadable after subsequent source/test edits.
        assert artifacts(request('/api/runs/'+run['id']))==count
        results.append({'project_id':pid,'run_id':run['id'],'language':extension,'runtime':'runsc','image_id':run['image_id'],
                        'passed':2,'failed':1,'screenshots':count,'coverage':run['coverage']['totals'],
                        'bug_proof_replayed':True,'syntax_error_not_confirmed':True,'runtime_error_not_confirmed':True})
    print(json.dumps({'results':results,'llm':'explicit contract-test provider; real browser execution'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
