"""Free uploaded-project acceptance. Explicit offline fixture, never a live AI claim.

Credential is supplied via stdin, not argv/env/logs. Uses normal TLS verification
and an optional VPN dial address without changing the authenticated hostname.
"""
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
from uuid import UUID, uuid4
import zipfile

HOST = 'debugych.89-22-232-119.nip.io'
PORT = 9443
SSH_CONFIG = os.environ.get('DEBUGYCH_SSH_CONFIG', str(Path.home() / '.ssh' / 'config'))
REMOTE = 'cd /opt/debugych/releases/server10-3bba37d && docker compose -p debugych-server --env-file /etc/debugych/production.env -f docker-compose.yml -f infra/server/compose.yml'
SOURCE = 'def add(a, b):\n    return a - b\n'

class API:
    def __init__(self, token): self.token = token
    def request(self, method, path, data=None, content_type='application/json', expected=200):
        raw = socket.create_connection((HOST,PORT),timeout=12)
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
        connection = http.client.HTTPSConnection(HOST,PORT,timeout=15)
        connection.sock = tls
        headers={'Authorization':'Bearer '+self.token,'Content-Type':content_type}
        body = json.dumps(data).encode() if data is not None and content_type=='application/json' else data
        connection.request(method,path,body=body,headers=headers)
        response=connection.getresponse(); payload=response.read(); status=response.status; connection.close()
        assert self.token.encode() not in payload
        if status != expected: raise RuntimeError(f'{method} {path}: HTTP {status}, expected {expected}')
        return json.loads(payload) if payload[:1] in (b'{',b'[') else payload
    def wait(self, job):
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            current=self.request('GET','/api/runs/'+job['id'])
            if current['status']=='completed': return current
            if current['status'] in ('failed','cancelled'): raise RuntimeError('Control job failed; inspect authenticated run '+job['id'])
            time.sleep(0.5)
        raise TimeoutError('Control queue job deadline exceeded')
    def upload(self,pid,filename,content,expected=201):
        boundary='debugych'+uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/zip\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        return self.request('POST',f'/api/projects/{pid}/files',body,'multipart/form-data; boundary='+boundary,expected)

def seed(pid,bid=None):
    UUID(pid)
    args=pid
    if bid: UUID(bid);args+=' --bug-id '+bid
    program=Path('scripts/server-control-fixture.py').read_text(encoding='utf-8')
    result=subprocess.run(['ssh','-F',SSH_CONFIG,'repair-vps',REMOTE+' exec -T api python - '+args],input=program,text=True,capture_output=True)
    if result.returncode:raise RuntimeError('Private fixture seed failed. No credentials emitted.')
    return json.loads(result.stdout)

def run(token):
    api=API(token)
    project=api.request('POST','/api/projects',{'name':'Server 1.0 offline control'},expected=201);pid=project['id']
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('calc.py',SOURCE)
        z.writestr('requirements.md','R1: add(a,b) returns the arithmetic sum of its two inputs.\nOffline infrastructure fixture; no new LLM generation.\n')
    api.upload(pid,'control.zip',archive.getvalue())
    attack=io.BytesIO()
    with zipfile.ZipFile(attack,'w') as z:z.writestr('../escape.py','raise AssertionError("must never execute")')
    api.upload(pid,'invalid.zip',attack.getvalue(),expected=422)
    plan=seed(pid)
    original=api.wait(api.request('POST',f'/api/projects/{pid}/runs',expected=202))
    assert original['runtime']=='runsc' and original['passed']==1 and original['failed']==1 and original['errors']==0
    bugs=api.request('GET','/api/bugs?project_id='+pid);assert len(bugs)==1;bug=bugs[0]
    proof=api.wait(api.request('POST',f"/api/bugs/{bug['id']}/confirm-proof",{'confirm_expectation':True,'reviewer_note':'Offline control requirement explicitly requires addition: 2 + 3 = 5. No generated expectation inferred from implementation.','run_id':original['id'],'test_sha256':bug['test_sha256']},expected=202))
    bug=api.request('GET','/api/bugs/'+bug['id']);assert bug['status']=='confirmed' and bug['proof_id']
    proposal=seed(pid,bug['id'])
    verification=api.wait(api.request('POST',f"/api/bugs/{bug['id']}/verify-fix",{'fix_id':proposal['fix_id']},expected=202))
    assert verification['verified'] and verification['runtime']=='runsc' and verification['passed']==2 and verification['assessment']['tests_unchanged']
    api.request('POST',f"/api/bugs/{bug['id']}/apply-fix",{'confirm':False},expected=409)
    fixes=api.request('GET',f'/api/projects/{pid}/fixes');assert fixes[0]['verified'] and not fixes[0]['applied']
    saved=api.request('GET',f'/api/projects/{pid}/source-archive')
    with zipfile.ZipFile(io.BytesIO(saved)) as z:assert z.read('calc.py').decode()==SOURCE
    stats=api.request('GET',f'/api/projects/{pid}/ai-statistics');assert stats['attempts']==0
    return {'classification':'FREE_OFFLINE_CONTROL_PASS','liveAI':'NOT RUN','newLLMCalls':0,'project_id':pid,'bug_id':bug['id'],'fix_id':proposal['fix_id'],'run_id':original['id'],'proof_run_id':proof['id'],'verification_id':verification['id'],
            'uploadedArchive':True,'invalidArchiveRejected':True,'baseline':{'passed':1,'failed':1,'errors':0},'regression':{'passed':2,'failed':0,'runtime':'runsc'},'testsUnchanged':True,'applied':False,'sourceUnchanged':True,'explicitApplyConfirmationRequired':True,'testAndPatchOrigin':'Known offline acceptance fixtures, NOT generated by LLM in this run'}

if __name__ == '__main__':
    token=json.load(sys.stdin)['token']
    report=run(token)
    Path('outputs/server10/vps-control-e2e.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
