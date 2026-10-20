import base64
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.db import Session,add_record
from apps.api.run_artifacts import persist,directory
from tests.unit.test_browser_profile import png

def test_download_is_bound_to_run_and_rejects_tampered_storage():
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'Artifact boundary'}).json()['id']
        result=persist({'artifacts':[{'name':'screenshot-1.png','media_type':'image/png','data':base64.b64encode(png()).decode()}]})
        with Session() as db:
            run=add_record(db,pid,'run',{'status':'completed',**result})
            other=add_record(db,pid,'run',{'status':'completed'})
            db.commit();rid,other_id=run.id,other.id
        artifact=result['artifacts'][0]
        assert 'data' not in artifact
        response=client.get(f'/api/runs/{rid}/artifacts/{artifact["id"]}')
        assert response.status_code==200 and response.content==png()
        assert response.headers['x-content-type-options']=='nosniff'
        assert response.headers['content-disposition'].startswith('attachment;')
        assert client.get(f'/api/runs/{other_id}/artifacts/{artifact["id"]}').status_code==404
        assert client.get(f'/api/runs/{rid}/artifacts/not-uuid').status_code==422
        (directory()/artifact['id']).write_bytes(b'tampered')
        assert client.get(f'/api/runs/{rid}/artifacts/{artifact["id"]}').status_code==409
