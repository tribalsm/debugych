"""Trusted control plane. Only this service may access the Docker socket.

Every uploaded snapshot gets a disposable mandatory-gVisor container. The
container never receives this socket, host paths, network, or credentials.
"""
import hmac
import json
import os
import threading
import time
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import uuid4
import docker
from docker.types import LogConfig, Ulimit
from fastapi import FastAPI, Header, HTTPException, Depends
from services.runner.contracts import SandboxJob, SandboxResult

IMAGE = os.getenv('SANDBOX_IMAGE','debugych-sandbox:local')
PLAYWRIGHT_IMAGE = os.getenv('PLAYWRIGHT_IMAGE','debugych-playwright:local')
RUNTIME = 'runsc'  # Fail closed; intentionally no environment override to runc.
LABEL = 'debugych.sandbox'
slots = threading.BoundedSemaphore(2)
client = None

def connection():
    global client
    if client is None:
        client = docker.from_env(timeout=60)
    return client

def authenticate(authorization: str = Header(default='')):
    token = Path(os.environ['RUNNER_TOKEN_FILE']).read_text().strip() if os.getenv('RUNNER_TOKEN_FILE') else os.getenv('RUNNER_TOKEN','')
    if len(token) < 32 or not hmac.compare_digest(authorization, 'Bearer '+token):
        raise HTTPException(401,'Runner authorization required')

def available(profile=None):
    daemon = connection()
    if RUNTIME not in daemon.info().get('Runtimes',{}):
        raise RuntimeError('gVisor runsc is required; untrusted execution is disabled')
    return daemon.images.get(PLAYWRIGHT_IMAGE if profile=='playwright' else IMAGE).id

def reap():
    while True:
        try:
            for container in connection().containers.list(all=True,filters={'label':LABEL+'=1'}):
                if float(container.labels.get('debugych.deadline','0')) < time.time():
                    container.remove(force=True,v=True)
        except Exception:
            pass
        time.sleep(10)

@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=reap,daemon=True).start()
    yield

app = FastAPI(title='DEBUGYCH gVisor supervisor',lifespan=lifespan,docs_url=None,redoc_url=None)

@app.get('/health')
def health():
    try:
        image = available()
        try:
            browser=available('playwright')
        except Exception:
            browser=None
        return {'status':'ok','execution':'gvisor-python','runtime':RUNTIME,'image_id':image,'playwright_image_id':browser}
    except Exception as error:
        raise HTTPException(503,str(error)) from error

def policy(job, image_id):
    browser=job.profile=='playwright'
    return dict(image=image_id,name='debugych-job-'+uuid4().hex, runtime=RUNTIME,
                user='10000:10000',network_mode='none',read_only=True,cap_drop=['ALL'],
                security_opt=['no-new-privileges:true'],mem_limit='1024m' if browser else '384m',memswap_limit='1024m' if browser else '384m',
                nano_cpus=1000000000,pids_limit=256 if browser else 128,init=False,stdin_open=True,tty=False,
                tmpfs={'/tmp':f'rw,nosuid,nodev,noexec,size={"192m" if browser else "96m"},uid=10000,gid=10000,mode=700'},
                ulimits=[Ulimit(name='nofile',soft=512 if browser else 128,hard=512 if browser else 128),Ulimit(name='core',soft=0,hard=0),Ulimit(name='fsize',soft=8000000,hard=8000000)],
                environment={'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1'},
                labels={LABEL:'1','debugych.job_id':str(job.id),'debugych.deadline':str(time.time()+90)},
                log_config=LogConfig(type=LogConfig.types.JSON,config={'max-size':'5m' if browser else '1m','max-file':'1'}))

def execute_snapshot(job):
    daemon = connection()
    image_id = available(job.profile)
    if job.expected_image_id and job.expected_image_id!=image_id:
        raise RuntimeError('Sandbox image changed; replay the project on the current reviewed image first')
    container = None
    start = time.monotonic()
    try:
        container = daemon.containers.create(**policy(job,image_id))
        # Attach stdin before start; a single newline-framed JSON envelope, no tar,
        # bind mounts, filenames interpreted by host tools, or user-controlled commands.
        stream = container.attach_socket(params={'stdin':1,'stream':1})
        try:
            container.start()
            stream._sock.settimeout(10)
            stream._sock.sendall(job.model_dump_json().encode()+b'\n')
        finally:
            stream.close()
        try:
            deadline=60 if job.profile=='playwright' else 45
            state = container.wait(timeout=deadline)
        except Exception:
            container.kill()
            return {'status':'failed','failure_kind':'timeout','error':f'Sandbox exceeded {deadline} second wall deadline','cases':[],'snapshot_sha256':job.fingerprint(),'runtime':RUNTIME,'image_id':image_id}
        container.reload()
        if container.attrs['State'].get('OOMKilled') or state['StatusCode'] != 0:
            return {'status':'failed','failure_kind':'sandbox_resource_or_process','error':'Sandbox terminated (resource limit or process exit)',
                    'exit_code':state['StatusCode'],'oom_killed':bool(container.attrs['State'].get('OOMKilled')),
                    'logs':container.logs(tail=20)[-4000:].decode('utf-8',errors='replace'),'cases':[],'snapshot_sha256':job.fingerprint(),'runtime':RUNTIME,'image_id':image_id}
        raw = container.logs(tail=1000)[-4000000:].decode('utf-8',errors='replace')
        lines = [line for line in raw.splitlines() if line.startswith('DEBUGYCH_RESULT=')]
        if not lines:
            raise RuntimeError('Sandbox returned no result envelope')
        result = SandboxResult.model_validate_json(lines[-1].split('=',1)[1]).model_dump(mode='json')
        # Results are observations from untrusted code; never confer Confirmed.
        if result.get('status') not in ('completed','failed') or not isinstance(result.get('cases'),list) or len(result['cases'])>1000:
            raise RuntimeError('Invalid sandbox result')
        allowed_ids = {str(t.id) for t in job.tests}
        if job.phase=='validate' and result['status']=='completed':
            check=result.get('validation')
            if not check:raise RuntimeError('Missing technical validation')
            items=check['collected']
            if any(c['test_id'] not in allowed_ids for c in items):raise RuntimeError('Unknown collected test')
            if check['discovery'] and (not check['syntax'] or not items or len({(c['test_id'],c['name']) for c in items})!=len(items)):
                raise RuntimeError('Invalid discovery evidence')
        if sum(len(a['data']) for a in result['artifacts'])>2800000 or len({a['name'] for a in result['artifacts']})!=len(result['artifacts']):
            raise RuntimeError('Artifact bundle exceeds limit or contains duplicates')
        if any(a.get('test_id') and a['test_id'] not in allowed_ids for a in result['artifacts']):
            raise RuntimeError('Artifact does not match submitted tests')
        for case in result['cases']:
            if case.get('test_id') not in allowed_ids or case.get('status') not in ('passed','failed','error','skipped'):
                raise RuntimeError('Sandbox result does not match submitted tests')
        for key,status in [('passed','passed'),('failed','failed'),('errors','error'),('skipped','skipped')]:
            result[key] = sum(case['status']==status for case in result['cases'])
        if result.get('coverage') and len(result['coverage']['files'])>100:
            raise RuntimeError('Too many coverage files')
        if result['status']=='failed' and not result.get('error'):
            result['error'] = (result.get('failure_kind') or 'Sandbox failed')+': '+result.get('logs','')[-800:]
        result.update(snapshot_sha256=job.fingerprint(),runtime=RUNTIME,image_id=image_id,supervisor_duration=round(time.monotonic()-start,3),trusted_demo=False,report_trust='untrusted-project-observation')
        return result
    finally:
        if container is not None:
            container.remove(force=True,v=True)

@app.post('/execute',dependencies=[Depends(authenticate)])
def execute(job: SandboxJob):
    if not slots.acquire(blocking=False):
        raise HTTPException(429,'Runner is at capacity; retry later')
    try:
        return execute_snapshot(job)
    except Exception as error:
        raise HTTPException(503,'Sandbox unavailable: '+str(error)[:500]) from error
    finally:
        slots.release()
