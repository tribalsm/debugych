import hashlib
from fastapi import FastAPI
from fastapi.testclient import TestClient
from apps.api.access import OwnerAccess

def setup(monkeypatch, tmp_path):
    path = tmp_path / 'hashes'
    path.write_text(hashlib.sha256(b'A'*64).hexdigest())
    monkeypatch.setenv('DEBUGYCH_SERVER', '1')
    monkeypatch.setenv('DEBUGYCH_AUTH_MODE', 'required')
    monkeypatch.setenv('DEBUGYCH_AUTH_HASHES_FILE', str(path))
    app = FastAPI()
    app.add_middleware(OwnerAccess)
    @app.api_route('/protected', methods=['GET','POST','OPTIONS'])
    async def protected():
        return {'ok': True}
    return TestClient(app), path

def test_all_routes_are_protected_including_docs_and_unknown_routes(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    for method in ['get', 'post', 'options']:
        for path in ['/protected', '/docs', '/openapi.json', '/api/projects', '/api/companion/ask', '/api/bugs/id/apply', '/unregistered']:
            assert getattr(client,method)(path).status_code == 401
    assert client.get('/healthz').json() == {'status':'alive'}
    assert client.get('/protected', headers={'Authorization':'Bearer '+'A'*64}).status_code == 200

def test_missing_config_and_auth_disabled_fail_closed_on_server(monkeypatch, tmp_path):
    client, path = setup(monkeypatch, tmp_path)
    path.unlink()
    assert client.get('/protected').status_code == 503
    monkeypatch.setenv('DEBUGYCH_AUTH_MODE','off')
    assert client.get('/protected').status_code == 503

def test_rotation_revokes_previous_token_without_restart(monkeypatch, tmp_path):
    client, path = setup(monkeypatch, tmp_path)
    path.write_text(hashlib.sha256(b'B'*64).hexdigest())
    assert client.get('/protected',headers={'Authorization':'Bearer '+'A'*64}).status_code == 401
    assert client.get('/protected',headers={'Authorization':'Bearer '+'B'*64}).status_code == 200

def test_duplicates_and_invalid_tokens_are_rejected(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    assert client.get('/protected',headers=[('Authorization','Bearer '+'A'*64),('Authorization','Bearer '+'A'*64)]).status_code == 401
    for token in ['A', 'B'*64, 'a'*1000]:
        assert client.get('/protected',headers={'Authorization':'Bearer '+token}).status_code == 401

def test_oversized_upload_rejected_before_handler(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    assert client.post('/protected',headers={'Authorization':'Bearer '+'A'*64,'Content-Length':str(50*1024*1024)}).status_code == 413

def test_provision_rotation_preserves_the_bound_inode(monkeypatch, tmp_path):
    import runpy
    provision = runpy.run_path('scripts/server-auth.py')['provision']
    client, path = setup(monkeypatch, tmp_path)
    before = path.stat().st_ino
    owner_file = tmp_path / 'owner-token'
    provision(path, owner_file)
    assert path.stat().st_ino == before
    assert client.get('/protected',headers={'Authorization':'Bearer '+'A'*64}).status_code == 401
    assert client.get('/protected',headers={'Authorization':'Bearer '+owner_file.read_text().strip()}).status_code == 200
