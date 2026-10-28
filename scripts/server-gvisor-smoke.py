"""Run fixed, free application workloads through the authenticated supervisor."""
import json
import os
import time
from uuid import uuid4
from apps.api.sandbox_client import execute

result = []
for profile in ['python', 'playwright']:
    test_id, requirement = str(uuid4()), str(uuid4())
    job = {'id':str(uuid4()), 'files':[{'path':'calc.py','content':'def add(a,b): return a+b'}],
           'tests':[{'id':test_id,'requirement_id':requirement,'code':'from calc import add\ndef test_add(): assert add(2,3)==5\n'}]}
    if profile == 'playwright':
        job.update(profile='playwright',files=[{'path':'index.html','content':'<!doctype html><h1>Debugych server smoke</h1>'}])
        job['tests'][0]['code']="import { test, expect } from '@playwright/test';\ntest('server smoke',async({page})=>{await page.goto('/');await expect(page.getByRole('heading')).toHaveText('Debugych server smoke')});"
    start = time.monotonic()
    observation = execute(job)
    assert observation['runtime'] == 'runsc' and observation['status'] == 'completed'
    assert observation['passed'] == 1 and observation['failed'] == 0 and observation['errors'] == 0
    result.append({'profile':profile,'runtime':observation['runtime'],'image_id':observation['image_id'],'passed':observation['passed'],'duration':round(time.monotonic()-start,3)})
print(json.dumps({'providerCalls':0,'workloads':result}))
