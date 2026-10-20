"""Execute via `docker compose exec -T supervisor python` with this file on stdin.

Boundary probes run only inside disposable gVisor containers. Nothing imports
or executes submitted code in this trusted supervisor process.
"""
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
from uuid import uuid4
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot, connection, LABEL, policy, available

# Authentication and unknown Docker-option injection are checked over real HTTP.
envelope=SandboxJob(id=uuid4(),files=[{'path':'source.py','content':'value=1'}],tests=[{'id':uuid4(),'requirement_id':uuid4(),'code':'def test_one(): assert True'}])
token=Path(os.environ['RUNNER_TOKEN_FILE']).read_text().strip()
for authorization,extra,expected in [('',{},401),('Bearer invalid',{},401),('Bearer '+token,{'privileged':True},422),('Bearer '+token,{'expected_image_id':'sha256:'+'0'*64},503)]:
    req=urllib.request.Request('http://127.0.0.1:8091/execute',data=json.dumps({**envelope.model_dump(mode='json'),**extra}).encode(),headers={'Content-Type':'application/json','Authorization':authorization})
    try:
        urllib.request.urlopen(req,timeout=5)
        raise AssertionError('Supervisor accepted unauthorized or malformed job')
    except urllib.error.HTTPError as error:
        assert error.code==expected,error.code
probe=connection().containers.create(**policy(envelope,available()))
try:
    probe.reload()
    host=probe.attrs['HostConfig']
    assert host['Runtime']=='runsc' and host['ReadonlyRootfs'] and host['NetworkMode']=='none'
    assert host['Memory']==384*1024*1024 and host['MemorySwap']==host['Memory']
    assert host['NanoCpus']==1000000000 and host['PidsLimit']==128
    assert not probe.attrs['Mounts']
    print('AUTH AND DOCKER POLICY CHECKS PASSED',flush=True)
finally:
    probe.remove(force=True,v=True)

code='''
import os, socket, pathlib, resource
import pytest

def test_boundary():
    assert os.getuid()==10000
    assert not pathlib.Path('/var/run/docker.sock').exists()
    assert not pathlib.Path('/data').exists()
    assert not pathlib.Path('/run/runner-token').exists()
    assert not any(k in os.environ for k in ['LLM_API_KEY','DATABASE_URL','REDIS_URL','RUNNER_TOKEN','RUNNER_TOKEN_FILE'])
    with pytest.raises(OSError): os.setuid(0)
    with pytest.raises(OSError): pathlib.Path('/opt/harness.py').write_text('overwritten')
    with pytest.raises(OSError): pathlib.Path('/etc/host-write').write_text('overwritten')
    s=socket.socket(); s.settimeout(.3)
    try:
        with pytest.raises(OSError): s.connect(('1.1.1.1',80))
    finally: s.close()
    status=pathlib.Path('/proc/self/status').read_text()
    assert 'NoNewPrivs:\\t1' in status
    assert 'CapEff:\\t0000000000000000' in status
    assert resource.getrlimit(resource.RLIMIT_NOFILE)==(128,128)
    assert resource.getrlimit(resource.RLIMIT_NPROC)==(16,16)

def test_process_limit():
    import subprocess, sys
    script="""
import os, signal, time
children=[]
blocked=False
try:
    for _ in range(24):
        try: pid=os.fork()
        except OSError:
            blocked=True
            break
        if pid==0:
            time.sleep(15)
            os._exit(0)
        children.append(pid)
    assert blocked, 'NPROC must block further children'
finally:
    for pid in children:
        try: os.kill(pid,signal.SIGKILL)
        except ProcessLookupError: pass
    for pid in children:
        try: os.waitpid(pid,0)
        except ChildProcessError: pass
"""
    assert subprocess.run([sys.executable,'-S','-c',script],timeout=12).returncode==0
'''

def run(code):
    job=SandboxJob(id=uuid4(),files=[{'path':'source.py','content':'value=1'}],tests=[{'id':uuid4(),'requirement_id':uuid4(),'code':code}])
    p=policy(job,available())
    assert p['runtime']=='runsc' and p['network_mode']=='none' and p['read_only']
    assert 'volumes' not in p and 'mounts' not in p and p['cap_drop']==['ALL']
    result=execute_snapshot(job)
    print(json.dumps(result,ensure_ascii=True),flush=True)
    assert not connection().containers.list(all=True,filters={'label':[LABEL+'=1','debugych.job_id='+str(job.id)]}),'Sandbox leaked'
    return result

result=run(code)
assert result['status']=='completed' and result['passed']==2 and result['failed']==0,result
result=run('def test_memory_limit():\n    data=bytearray(600*1024*1024)\n    assert len(data)>0\n')
assert result['status']=='failed',result
result=run('def test_wall_timeout():\n    import time\n    time.sleep(100)\n')
assert result['status']=='failed',result
print('SECURITY PROBES PASSED: identity, secrets, mounts, rootfs, capabilities, network, NPROC, memory, time and cleanup',flush=True)
