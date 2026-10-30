"""Opt-in CI package proof on an authenticated HTTPS server. No model or patch routes."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import UUID, uuid4
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.api.ci_client import Client


def main():
    if os.getenv('DEBUGYCH_CI_LIVE_CHECK')!='1':raise SystemExit('Set DEBUGYCH_CI_LIVE_CHECK=1 explicitly')
    base=os.environ['DEBUGYCH_BASE_URL'];credentials=json.loads(Path(os.environ['DEBUGYCH_ACCOUNT_CREDENTIALS']).read_text(encoding='utf-8'))
    user=next(a for a in credentials['accounts'] if a['role']=='jury')
    client=Client(base);client.login(user['username'],user['password'])
    out=Path('outputs/server10/metrics-ci');out.mkdir(parents=True,exist_ok=True)
    results=[]
    fixtures=[('pytest',{'calc.py':'def add(a,b): return a+b\n','test_calc.py':'from calc import add\ndef test_add(): assert add(1,2)==3\ndef test_zero(): assert add(-1,1)==0\n'},'calc.py','def add(a,b): return a-b\n',2),
              ('playwright',{'index.html':'<h1>Counter</h1><button>0</button><script type="module" src="/app.js"></script>','app.js':"const b=document.querySelector('button');b.onclick=()=>{b.textContent=String(Number(b.textContent)+1)};",'counter.spec.ts':"import {test,expect} from '@playwright/test';test('counter',async({page})=>{await page.goto('/');await page.getByRole('button').click();await expect(page.getByRole('button')).toHaveText('1')});"},'app.js',"const b=document.querySelector('button');b.onclick=()=>{b.textContent=String(Number(b.textContent)+2)};",1)]
    for profile,files,source,broken,count in fixtures:
        pid=None
        try:
            pid=str(UUID(client.json('POST','/api/projects',{'name':'CI export control '+profile})['id']))
            for name,content in files.items():
                boundary=uuid4().hex;body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/plain\r\n\r\n{content}\r\n--{boundary}--\r\n').encode()
                client.request('POST',f'/api/projects/{pid}/files',body,'multipart/form-data; boundary='+boundary)
            client.json('POST',f'/api/projects/{pid}/import-tests',{})
            payload=client.request('GET',f'/api/exports?project_id={pid}&format=ci')
            with tempfile.TemporaryDirectory(prefix='debugych-ci-proof-') as directory:
                root=Path(directory)
                # Archive is produced by our trusted backend, not an uploaded ZIP.
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:archive.extractall(root)
                for name,content in files.items():(root/name).write_text(content,encoding='utf-8')
                for phase in ('pass','fail'):
                    if phase=='fail':(root/source).write_text(broken,encoding='utf-8')
                    output=root/'debugych-report';env={**os.environ,'DEBUGYCH_USERNAME':user['username'],'DEBUGYCH_PASSWORD':user['password']}
                    process=subprocess.run([sys.executable,str(root/'debugych_ci/run.py'),'--root',str(root),'--output',str(output)],env=env,capture_output=True,timeout=360)
                    # Never output subprocess bodies: a malicious server could echo credentials.
                    expected=0 if phase=='pass' else 1
                    assert process.returncode==expected,f'{profile} {phase}: client exit {process.returncode}'
                    summary=json.loads((output/'summary.json').read_text());xml=ET.parse(output/'junit.xml').getroot()
                    assert summary['runtime']=='runsc' and summary['tests']==count
                    assert summary['failures']==(0 if phase=='pass' else count)
                    assert summary['errors']==0 and xml.attrib['tests']==str(count)
                    (out/f'{profile}-{phase}-junit.xml').write_bytes((output/'junit.xml').read_bytes())
                    results.append({'profile':profile,'phase':phase,'exit':process.returncode,**summary})
            assert client.json('GET',f'/api/projects/{pid}/ai-statistics')['attempts']==0
        finally:
            if pid:client.json('DELETE',f'/api/projects/{pid}')
    (out/'live-results.json').write_text(json.dumps({'results':results,'llm_requests':0,'patch_applications':0},indent=2),encoding='utf-8')
    print(json.dumps(results))


if __name__=='__main__':main()
