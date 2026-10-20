import json
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.db import Session,Record,add_record
from apps.api.bug_workflow import digest
from services.ai.engine import Plan


def seed(c):
    pid=c.post('/api/projects',json={'name':'Explicit draft review'}).json()['id']
    c.post(f'/api/projects/{pid}/files',files={'file':('app.py',b'def charge(n): return n')})
    c.post(f'/api/projects/{pid}/files',files={'file':('requirements.md',b'R1. Charge returns the amount.')})
    state=c.get(f'/api/projects/{pid}/ai-context').json()['project_state_sha256']
    plan=Plan.model_validate({'requirements':[{'key':'R1','text':'Charge returns the amount.'}],
        'scenarios':[{'title':'Charge','requirement':'R1','framework':'pytest','gherkin':'Feature: Charge\nScenario: Amount',
            'code':'from app import charge\ndef test_charge(): assert charge(1)==1'}]}).model_dump()
    with Session() as db:
        row=add_record(db,pid,'run',{'operation':'analyze','status':'failed','error':'test_review_rejected',
            'ai_consent':{'project_state_sha256':state},'generation_review':{'drafts':[{'plan':plan,'review':{'approved':False,'issues':['Advisory complaint']}}]}})
        db.commit();analysis_id=row.id
    return pid,plan,{'confirm':True,'analysis_id':analysis_id,'draft_index':0,
        'draft_sha256':digest(json.dumps(plan,sort_keys=True,ensure_ascii=False)),
        'project_state_sha256':state,'reviewer_kind':'agent','reviewer_note':'Reviewed each unchanged assertion against public R1.'}


def test_accept_unchanged_ai_draft_keeps_failed_analysis_and_provenance():
    with TestClient(app) as c:
        pid,plan,body=seed(c)
        response=c.post(f'/api/projects/{pid}/accept-ai-draft',json=body)
        assert response.status_code==201,response.text
        tests=c.get(f'/api/projects/{pid}/test-cases').json()
        assert tests[0]['code']==plan['scenarios'][0]['code']
        assert tests[0]['origin']=='llm-reviewed-draft'
        assert tests[0]['draft_review']['reviewer_kind']=='agent'
        assert c.get('/api/runs/'+body['analysis_id']).json()['status']=='failed'
        assert c.post(f'/api/projects/{pid}/accept-ai-draft',json=body).status_code==409


@pytest.mark.parametrize('changes,status',[
    ({'confirm':False},409),({'draft_sha256':'0'*64},409),
    ({'project_state_sha256':'0'*64},409),({'draft_index':1},404),
    ({'analysis_id':str(uuid4())},404),({'reviewer_kind':'automatic'},422)])
def test_draft_review_fails_closed(changes,status):
    with TestClient(app) as c:
        pid,plan,body=seed(c)
        assert c.post(f'/api/projects/{pid}/accept-ai-draft',json={**body,**changes}).status_code==status
        assert c.get(f'/api/projects/{pid}/test-cases').json()==[]
        assert c.get(f'/api/projects/{pid}/requirements').json()==[]


def test_draft_review_rejects_changed_source_and_active_job():
    with TestClient(app) as c:
        pid,plan,body=seed(c)
        with Session() as db:
            row=add_record(db,pid,'run',{'operation':'run','status':'queued'});db.commit();active=row.id
        assert c.post(f'/api/projects/{pid}/accept-ai-draft',json=body).status_code==409
        with Session() as db:
            row=db.get(Record,active);row.data={**row.data,'status':'failed'};db.commit()
        c.post(f'/api/projects/{pid}/files',files={'file':('extra.py',b'# changed')})
        assert c.post(f'/api/projects/{pid}/accept-ai-draft',json=body).status_code==409
