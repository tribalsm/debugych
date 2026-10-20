"""Real runsc syntax/discovery checks, zero external LLM requests."""
import json,subprocess,os
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]

def main():
    cases=[('python-discovery',None,'from calc import add\ndef test_sum(): assert add(1,2)==3',True,True),
           ('python-syntax',None,'def test_bad(: pass',False,False),
           ('python-no-tests',None,'x=1',True,False),
           ('python-product-failure-is-not-discovery-failure',None,'from calc import add\ndef test_sum(): assert add(1,2)==999',True,True),
           ('typescript-discovery','playwright',"import {test,expect} from '@playwright/test';test('one',async({page})=>{await page.goto('/');await expect(page.locator('h1')).toHaveText('Hello');});",True,True),
           ('typescript-syntax','playwright',"import {test} from '@playwright/test';test('bad',async(=>{});",False,False),
           ('typescript-duplicate-title','playwright',"import {test} from '@playwright/test';test('same',()=>{});test('same',()=>{});",True,False)]
    jobs=[]
    for label,profile,code,syntax,discovery in cases:
        files=[{'path':'index.html','content':'<h1>Hello</h1>'}] if profile else [{'path':'calc.py','content':'def add(a,b): return a+b'}]
        jobs.append({'label':label,'syntax':syntax,'discovery':discovery,'job':{'id':str(uuid4()),'phase':'validate','profile':profile,
            'files':files,'tests':[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':code}]}})
    script='from services.runner.supervisor import execute_snapshot\nfrom services.runner.contracts import SandboxJob\nimport json\njobs='+repr(jobs)+'''\nrows=[]
for item in jobs:
    result=execute_snapshot(SandboxJob.model_validate(item['job']))
    check=result.get('validation',{})
    assert result.get('runtime')=='runsc' and check.get('syntax')==item['syntax'] and check.get('discovery')==item['discovery'], (item['label'],result)
    rows.append({'label':item['label'],'runtime':result['runtime'],'validation':check,'image_id':result['image_id']})
print(json.dumps(rows))
'''
    cmd=['docker','compose','exec','-T','supervisor','python']
    if os.name=='nt':cmd=['wsl','-d','Ubuntu','-u','root','--cd','/mnt/'+ROOT.drive[0].lower()+ROOT.as_posix()[2:],'--',*cmd]
    run=subprocess.run(cmd,input=script.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,timeout=240)
    if run.returncode:raise RuntimeError(run.stderr.decode()[-4000:])
    data=json.loads(run.stdout);(ROOT/'work/validation-gvisor.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({'gvisor_checks_passed':len(data),'external_llm_requests':0}))

if __name__=='__main__':main()
