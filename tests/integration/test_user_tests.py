import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.db import Session,Record,add_record
from apps.api.jobs import DATA
from apps.api.snapshots import snapshot_project

def upload(client,pid,name,code):
    assert client.post(f'/api/projects/{pid}/files',files={'file':(name,code.encode())}).status_code==201

@pytest.mark.parametrize('framework,name,code,source,content',[
    ('pytest','test_calc.py','from calc import add\ndef test_add(): assert add(1,2)==3','calc.py','def add(a,b): return a+b'),
    ('playwright','page.spec.ts',"import {test,expect} from '@playwright/test';test('page',async({page})=>{await page.goto('/');await expect(page.locator('h1')).toHaveText('Hello')})",'index.html','<h1>Hello</h1>'),
])
def test_import_user_tests_data_only_and_snapshot(framework,name,code,source,content,monkeypatch):
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'User tests'}).json()['id']
        upload(client,pid,source,content);upload(client,pid,name,code)
        response=client.post(f'/api/projects/{pid}/import-tests');assert response.status_code==201,response.text
        tests=response.json()['tests'];assert len(tests)==1
        assert tests[0]['origin']=='uploaded-user-tests' and tests[0]['result']=='not_run'
        assert tests[0]['code']==code and tests[0]['framework']==framework
        assert client.get('/api/test-cases/'+tests[0]['id']).json()['project_id']==pid
        with Session() as db:
            snapshot=snapshot_project(db,pid)
        assert [f['path'] for f in snapshot['files']]==[source]
        assert snapshot['tests'][0]['code']==code
        assert client.post(f'/api/projects/{pid}/import-tests').status_code==409
        assert client.post(f'/api/projects/{pid}/runs').status_code==403  # No sandbox, no execution in backend.

@pytest.mark.parametrize('code',[
    'def test_broken(: pass',
    'from .calc import add\ndef test_add(): pass',
    'import os\nos.environ["SHOULD_NOT_EXECUTE"]="yes"',
])
def test_invalid_tests_not_executed_or_saved(code,monkeypatch):
    import os
    monkeypatch.delenv('SHOULD_NOT_EXECUTE',raising=False)
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'Invalid user test'}).json()['id'];upload(client,pid,'test_bad.py',code)
        assert client.post(f'/api/projects/{pid}/import-tests').status_code==422
        assert client.get(f'/api/projects/{pid}/test-cases').json()==[]
        assert client.get(f'/api/projects/{pid}/requirements').json()==[]
        assert 'SHOULD_NOT_EXECUTE' not in os.environ

def test_delete_project_busy_guard_and_physical_files():
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'Delete'}).json()['id'];upload(client,pid,'calc.py','pass')
        with Session() as db:
            rows=db.query(Record).filter_by(project_id=pid,kind='file').all();storage=rows[0].data['storage']
            job=add_record(db,pid,'run',{'status':'queued'});db.commit();jid=job.id
        assert client.delete('/api/projects/'+pid).status_code==409
        assert (DATA/storage).exists()
        with Session() as db:
            job=db.get(Record,jid);job.data={'status':'failed'};db.commit()
        assert client.delete('/api/projects/'+pid).status_code==200
        assert not (DATA/storage).exists()
        assert client.get('/api/projects/'+pid).status_code==404
        assert client.get('/api/runs/'+jid).status_code==404

def test_no_tests_and_mixed_frameworks_rejected():
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'Mixed'}).json()['id']
        assert client.post(f'/api/projects/{pid}/import-tests').status_code==422
        upload(client,pid,'test_one.py','def test_one(): pass');upload(client,pid,'two.spec.ts','// Playwright')
        assert client.post(f'/api/projects/{pid}/import-tests').status_code==422
        assert client.get(f'/api/projects/{pid}/requirements').json()==[]
