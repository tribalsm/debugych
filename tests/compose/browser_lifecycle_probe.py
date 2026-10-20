"""Run inside our trusted supervisor; test code still executes only in gVisor.

Failing assertions must restart workers without relaunching the job's browser.
Contexts, cookies and localStorage must remain isolated across those restarts.
No provider calls, source edits, retries or additional runtime budget.
"""
import base64
import json
import re
import sys
from uuid import UUID, uuid4
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot, policy, available
from services.runner import supervisor

baseline = '--baseline' in sys.argv
if baseline:
    supervisor.PLAYWRIGHT_IMAGE = 'debugych-playwright:local'

tests = []
for i in range(6):
    assertion = "expect(1).toBe(2);" if i in (0, 2, 4) else "expect(1).toBe(1);"
    tests.append({
        'id': UUID(int=i + 1), 'requirement_id': uuid4(),
        'code': """import {test,expect} from '@playwright/test';
import fs from 'node:fs';
test('fresh context %s',async({page})=>{
 for(const pid of fs.readdirSync('/proc').filter(p=>/^[0-9]+$/.test(p))) {
   try {const cmd=fs.readFileSync('/proc/'+pid+'/cmdline','utf8');if(cmd.includes('--remote-debugging-pipe')&&!cmd.includes('--type=')) console.log('LIFECYCLE_BROWSER_PID='+pid);} catch {}
 }
 await page.goto('/');
 expect(await page.evaluate(()=>localStorage.getItem('previous'))).toBeNull();
 expect(await page.context().cookies()).toEqual([]);
 await page.evaluate(()=>{localStorage.setItem('previous','dirty');document.cookie='previous=dirty';});
 await expect(page.getByRole('heading')).toHaveText('Lifecycle probe');
 %s
});""" % (i, assertion),
    })
job = SandboxJob(id=uuid4(), profile='playwright', files=[{
    'path': 'index.html', 'content': '<h1>Lifecycle probe</h1>'}], tests=tests)
config = policy(job, available('playwright'))
assert config['runtime'] == 'runsc' and config['network_mode'] == 'none'
assert config['nano_cpus'] == 1000000000 and config['pids_limit'] == 256
assert config['mem_limit'] == config['memswap_limit'] == '1024m'
if not baseline:
    validation = execute_snapshot(job.model_copy(update={'phase':'validate'}))
    assert validation['status'] == 'completed' and validation['validation']['discovery'], validation
    assert len(validation['validation']['collected']) == 6, validation
    assert 'DEBUGYCH_BROWSER_READY_MS=' not in validation['logs'], validation
result = execute_snapshot(job)
if baseline:
    print(json.dumps({
        **{k:result.get(k) for k in ('status','runtime','image_id','duration','passed','failed','errors','error','logs')},
        'browser_pids': sorted(set(re.findall(r'LIFECYCLE_BROWSER_PID=([0-9]+)', result.get('logs','')))),
    }), flush=True)
    sys.exit(0)
assert result['status'] == 'completed', result
assert (result['passed'], result['failed'], result['errors']) == (3, 3, 0), result
assert result['logs'].count('DEBUGYCH_BROWSER_READY_MS=') == 1, result['logs']
pids = sorted(set(re.findall(r'LIFECYCLE_BROWSER_PID=([0-9]+)', result['logs'])))
assert len(pids) == 1, pids
report = next(a for a in result['artifacts'] if a['name'] == 'playwright-report.json')
report = json.loads(base64.b64decode(report['data']))
workers = [o['worker_index'] for o in report['browser_observations']]
assert len(set(workers)) >= 3, workers
assert len([a for a in result['artifacts'] if a['media_type'] == 'image/png']) == 6
print(json.dumps({
    'status': result['status'], 'runtime': result['runtime'], 'image_id': result['image_id'],
    'duration': result['duration'], 'stats': report['stats'], 'worker_indices': workers,
    'browser_launches': result['logs'].count('DEBUGYCH_BROWSER_READY_MS='),
    'browser_pids': pids,
    'isolated_contexts': 6, 'screenshots': 6, 'llm_requests': 0,
    'discovery_without_browser': True,
}), flush=True)
