"""Execute inside trusted supervisor. Submitted JS runs only in gVisor."""
import json
from uuid import uuid4
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot,policy,available,connection,LABEL

def run(code):
    job=SandboxJob(id=uuid4(),profile='playwright',files=[{'path':'index.html','content':'<h1>Isolation probe</h1>'}],
                   tests=[{'id':uuid4(),'requirement_id':uuid4(),'code':code}])
    config=policy(job,available('playwright'))
    assert config['runtime']=='runsc' and config['network_mode']=='none' and config['read_only']
    assert config['user']=='10000:10000' and config['mem_limit']==config['memswap_limit']=='1024m'
    assert config['pids_limit']==256 and config['nano_cpus']==1000000000 and config['cap_drop']==['ALL']
    assert not config.get('volumes') and not config.get('mounts') and not config.get('ipc_mode')
    result=execute_snapshot(job)
    assert not connection().containers.list(all=True,filters={'label':[LABEL+'=1','debugych.job_id='+str(job.id)]})
    print(json.dumps({k:v for k,v in result.items() if k!='artifacts'},ensure_ascii=True),flush=True)
    return result

code='''import {test,expect} from '@playwright/test';
import fs from 'node:fs';
import net from 'node:net';
test('isolation and real browser',async({page})=>{
 expect(process.getuid()).toBe(10000);
 for(const key of ['LLM_API_KEY','RUNNER_TOKEN','DATABASE_URL']) expect(process.env[key]).toBeUndefined();
 expect(fs.existsSync('/var/run/docker.sock')).toBe(false);
 expect(fs.existsSync('/run/runner-token/token')).toBe(false);
 expect(()=>fs.writeFileSync('/opt/runtime/probe','bad')).toThrow();
 const status=fs.readFileSync('/proc/self/status','utf8');
 expect(status).toContain('CapEff:\\t0000000000000000');
 const reachable=await new Promise(resolve=>{const socket=net.connect({host:'1.1.1.1',port:443});socket.setTimeout(600);socket.on('connect',()=>{socket.destroy();resolve(true)});socket.on('error',()=>resolve(false));socket.on('timeout',()=>{socket.destroy();resolve(false)});});
 expect(reachable).toBe(false);
 await page.goto('/');await expect(page.getByRole('heading')).toHaveText('Isolation probe');
 await expect(page.goto('https://example.com')).rejects.toThrow();
});'''
result=run(code)
assert result['status']=='completed' and result['passed']==1 and result['errors']==0,result
result=run("import {test} from '@playwright/test'; test('stuck worker',async()=>{while(true){}});")
assert result['status']=='failed' or result.get('errors',0)>0,result
print('PLAYWRIGHT SECURITY PROBES PASSED: non-root, no secrets/socket/host IPC, readonly root, no capabilities/network, cgroup limits, stuck-worker deadline and cleanup',flush=True)
