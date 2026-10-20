from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import main
from apps.api.ai_runtime import reserve
from services.ai.adapter import Settings,AIError

def test_consent_required_and_state_provider_bound(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','unit-test-key')
    monkeypatch.setattr(main,'dispatch',lambda *args:None)
    with TestClient(app) as c:
        pid=c.post('/api/projects',json={'name':'Consent guard'}).json()['id']
        c.post(f'/api/projects/{pid}/files',files={'file':('requirements.md',b'R1. Expected result.')})
        assert c.post(f'/api/projects/{pid}/analyze',json={}).status_code==422
        assert c.post(f'/api/projects/{pid}/analyze').status_code==428
        p=c.get(f'/api/projects/{pid}/ai-context').json()
        consent={'confirm':True,'project_state_sha256':p['project_state_sha256'],'provider_fingerprint':p['provider_fingerprint']}
        assert c.post(f'/api/projects/{pid}/analyze',json={'consent':{**consent,'confirm':False}}).status_code==428
        monkeypatch.setenv('LLM_MODEL','another-model')
        assert c.post(f'/api/projects/{pid}/analyze',json={'consent':consent}).status_code==409
        monkeypatch.delenv('LLM_MODEL',raising=False)
        c.post(f'/api/projects/{pid}/files',files={'file':('app.py',b'value=1')})
        assert c.post(f'/api/projects/{pid}/analyze',json={'consent':consent}).status_code==409
        assert c.get(f'/api/projects/{pid}/ai-statistics').json()['attempts']==0

def test_atomic_daily_reservations_survive_new_sessions(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER_MODE','contract-test')
    monkeypatch.setenv('LLM_MAX_DAILY_CALLS','2')
    settings=Settings.load()
    with TestClient(app):
        def attempt(_):
            try:reserve(100,10,settings);return True
            except AIError:return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            accepted=list(pool.map(attempt,range(4)))
        assert sum(accepted)==2
        with pytest.raises(AIError,match='daily_budget_exhausted'):reserve(1,1,settings)
