from uuid import uuid4
import pytest
from apps.api import main
from apps.api.db import Session, Record, add_record
from fastapi.testclient import TestClient

def test_fail_closed_when_supervisor_unavailable(monkeypatch):
    monkeypatch.setenv('SANDBOX_ENABLED','1')
    monkeypatch.setattr(main,'sandbox_health',lambda:None)
    with TestClient(main.app) as client:
        pid=client.post('/api/projects',json={'name':'Closed runner'}).json()['id']
        result=client.post(f'/api/projects/{pid}/runs')
        assert result.status_code==503
        assert client.get(f'/api/projects/{pid}/runs').json()==[]

def test_queued_run_freezes_exact_source_and_generated_code(monkeypatch):
    monkeypatch.setenv('SANDBOX_ENABLED','1')
    monkeypatch.setattr(main,'sandbox_health',lambda:{'runtime':'runsc'})
    monkeypatch.setattr(main,'dispatch',lambda *args:None)
    with TestClient(main.app) as client:
        pid=client.post('/api/projects',json={'name':'Snapshot contract'}).json()['id']
        client.post(f'/api/projects/{pid}/files',files={'file':('calc.py',b'def add(a,b): return a+b')})
        original='from calc import add\ndef test_add(): assert add(1,2)==3'
        with Session() as db:
            req=add_record(db,pid,'requirement',{'key':'R1','text':'Addition'})
            test=add_record(db,pid,'test',{'title':'Add','gherkin':'Feature: Add\nScenario: add','code':original,'framework':'pytest','requirement_id':req.id,'result':'not_run','origin':'llm','dimensions':['negative']})
            db.commit()
            tid=test.id
        job=client.post(f'/api/projects/{pid}/runs')
        assert job.status_code==202
        jid=job.json()['id']
        with Session() as db:
            snapshot=db.get(Record,jid).data['snapshot']
            quality_inputs=db.get(Record,jid).data['quality_inputs']
        assert quality_inputs=={'requirement_ids':[req.id],'tests':[{'id':tid,'requirement_id':req.id,'dimensions':['negative']}]}
        assert snapshot['id']==jid and snapshot['tests'][0]['code']==original
        client.patch('/api/test-cases/'+tid,json={'title':'Edited','gherkin':'Feature: Add\nScenario: add','code':'def test_new(): assert False'})
        with Session() as db:
            assert db.get(Record,jid).data['snapshot']['tests'][0]['code']==original
            assert db.get(Record,jid).data['quality_inputs']==quality_inputs
        assert 'snapshot' not in client.get('/api/runs/'+jid).json()
