from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.db import Base, engine, Session, Record
from apps.api import jobs
from services.runner.main import execute

def test_project_upload_and_execution_guard():
    with TestClient(app) as client:
        result = client.post('/api/projects', json={'name':'My API'})
        assert result.status_code == 201
        pid = result.json()['id']
        assert client.get(f'/api/projects/{pid}').json()['name'] == 'My API'
        assert client.post(f'/api/projects/{pid}/files', files={'file':('app.py',b'def add(a,b): return a+b')}).status_code == 201
        assert len(client.get(f'/api/projects/{pid}/files').json()) == 1
        assert client.post(f'/api/projects/{pid}/files', files={'file':('../app.py',b'pass')}).status_code == 422
        assert client.post(f'/api/projects/{pid}/runs').status_code == 403
        assert client.get('/api/projects/not-uuid').status_code == 422

def test_demo_full_proof_fix_verify_apply_export(monkeypatch):
    # Transport replaced with the real trusted runner function, never a fabricated result.
    class RunnerResponse:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data
    monkeypatch.setattr(jobs.httpx, 'post', lambda url, json, timeout: RunnerResponse(execute(json['fixed'])))
    with TestClient(app) as client:
        pid = client.post('/api/demo').json()['id']
        assert client.post(f'/api/projects/{pid}/files',files={'file':('app.py',b'pass')}).status_code == 409
        job = client.post(f'/api/projects/{pid}/analyze')
        assert job.status_code == 202
        assert client.get('/api/runs/'+job.json()['id']).json()['status'] == 'completed'
        assert len(client.get(f'/api/projects/{pid}/requirements').json()) == 4
        tests = client.get(f'/api/projects/{pid}/test-cases').json()
        assert 'test_exact_balance' in tests[0]['code']
        run = client.post(f'/api/projects/{pid}/runs').json()
        run = client.get('/api/runs/'+run['id']).json()
        assert run['status'] == 'completed'
        assert run['failed'] == 1
        assert run['passed'] == 13
        assert run['coverage']['totals']['percent_covered'] > 50
        assert client.get('/api/runs/'+run['id']+'/coverage').status_code == 200
        bug = client.get('/api/bugs', params={'project_id':pid}).json()[0]
        assert bug['status'] == 'confirmed'
        assert 'AssertionError' in bug['traceback']
        assert client.post('/api/bugs/'+bug['id']+'/apply-fix',json={'confirm':True}).status_code == 409
        proposal = client.post('/api/bugs/'+bug['id']+'/propose-fix').json()
        assert '+    return balance >= amount' in proposal['diff']
        verification = client.post('/api/bugs/'+bug['id']+'/verify-fix').json()
        verification = client.get('/api/runs/'+verification['id']).json()
        assert verification['status'] == 'completed'
        assert verification['failed'] == 0 and verification['passed'] == 14
        assert verification['assessment']['original_fixed']
        assert verification['assessment']['regressions_absent']
        assert client.post('/api/bugs/'+bug['id']+'/apply-fix',json={'confirm':False}).status_code == 409
        assert client.post('/api/bugs/'+bug['id']+'/apply-fix',json={'confirm':True}).json()['applied']
        rerun = client.post(f'/api/projects/{pid}/runs').json()
        assert client.get('/api/runs/'+rerun['id']).json()['failed'] == 0
        assert 'Feature:' in client.get('/api/exports',params={'project_id':pid,'format':'feature'}).text
        assert 'test_exact_balance' in client.get('/api/exports',params={'project_id':pid,'format':'py'}).text
        assert client.get('/api/exports',params={'project_id':pid,'format':'js'}).status_code == 404
