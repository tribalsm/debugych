"""LLM is a local MockTransport. Never sends external requests or executes code."""
import json
from pathlib import Path
from uuid import uuid4
import httpx,pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from apps.api.main import app
from apps.api.db import Session,Project,Record
from apps.api import companion_chat as chat
from services.ai.adapter import AIAdapter

@pytest.fixture
def setup(monkeypatch):
 monkeypatch.setenv('LLM_API_KEY','sk-companion-fixture-key-123456789');monkeypatch.setenv('LLM_MODEL','gpt-6-luna');monkeypatch.setenv('LLM_PROVIDER_MODE','contract-test')
 monkeypatch.setenv('LLM_MAX_DAILY_CALLS','1000');monkeypatch.setenv('LLM_MAX_DAILY_USD','1000')
 with TestClient(app):pass
 pid=str(uuid4());root=str(uuid4());original=str(uuid4());proof=str(uuid4());bid=str(uuid4());fid=str(uuid4());verify=str(uuid4());sha='a'*64
 with Session() as db:
  db.add(Project(id=pid,name='Companion contract',demo=False));db.flush()
  for rid,data in [(root,{'operation':'autonomous','status':'completed'}),(original,{'operation':'run','status':'completed','failed':1,'passed':7,'errors':0,'parent_workflow_id':root}),(proof,{'operation':'confirm_proof','status':'completed','bug_id':bid,'parent_workflow_id':root,'review':{'run_id':original,'test_sha256':sha},'assessment':{'reproduced_again':True,'requirement_reviewed':True,'infrastructure_excluded':True}}),(verify,{'operation':'verify','status':'completed','bug_id':bid,'fix_id':fid,'parent_workflow_id':root,'verified':True,'patch_sha256':sha,'passed':8,'failed':0,'errors':0,'assessment':{'original_fixed':True,'regressions_absent':True,'all_regression_passed':True}})]:db.add(Record(id=rid,project_id=pid,kind='run',data=data))
  db.add(Record(id=bid,project_id=pid,kind='bug',data={'status':'fix_verified','run_id':original,'proof_id':proof,'test_sha256':sha,'title':'Boundary','expected':'Equality accepted','actual':'False','traceback':'assert False is True'}))
  db.add(Record(id=fid,project_id=pid,kind='fix',data={'bug_id':bid,'proof_id':proof,'verified':True,'verification_id':verify,'patch_sha256':sha,'applied':False,'diff':'- return balance > amount\n+ return balance >= amount'}));db.commit()
 calls=[]
 def provider(request):
  body=json.loads(request.content);calls.append(body);payload=json.loads(body['messages'][1]['content'])
  return httpx.Response(200,json={'model':'gpt-6-luna','choices':[{'finish_reason':'stop','message':{'content':json.dumps({'explanation':'В сохранённом тесте нарушено ожидаемое равенство. Патч проверен и не применён.','hypotheses':['Другие граничные случаи требуют отдельной проверки.'],'evidence_ids':[payload['facts']['bug']['proof_id']]})}}],'usage':{'prompt_tokens':100,'completion_tokens':40}})
 monkeypatch.setattr(chat,'make_adapter',lambda s,audit:AIAdapter(s,transport=httpx.MockTransport(provider),reserve=chat.reserve,audit=audit,sleep=lambda _:None))
 with TestClient(app) as client:yield client,{'request_id':str(uuid4()),'project_id':pid,'root_run_id':root,'bug_id':bid,'fix_id':fid,'question':'Объясни ограничения проверки подробнее.'},calls

def grant(client,q):
 p=client.post('/api/companion/preview',json=q);assert p.status_code==200,p.text
 v=p.json();return {**q,'confirm':True,'context_sha256':v['context_sha256'],'provider_fingerprint':v['provider_fingerprint']}

def test_preview_is_free_redacted_and_does_not_leak_key(setup):
 c,q,calls=setup;q['question']+=' API_KEY="private-synthetic-value"'
 p=c.post('/api/companion/preview',json=q);assert p.status_code==200
 assert calls==[] and 'private-synthetic-value' not in p.text and 'sk-companion-fixture-key' not in p.text
 assert p.json()['max_calls']==1 and p.json()['max_reserved_usd']<=.25

def test_bound_mock_answer_citations_budget_audit_and_no_qa_mutation(setup):
 c,q,calls=setup;body=grant(c,q);r=c.post('/api/companion/ask',json=body);assert r.status_code==200,r.text
 assert r.json()['kind']=='llm' and r.json()['sources'][0]['target']['bugId']==q['bug_id'];assert len(calls)==1 and calls[0]['max_completion_tokens']<=1000
 with Session() as db:
  row=db.get(Record,q['request_id']);assert 'question' not in row.data and 'text' not in row.data
  assert db.get(Record,q['fix_id']).data['applied'] is False
  assert len(db.scalars(select(Record).where(Record.project_id==q['project_id'],Record.kind=='run')).all())==4
 assert c.post('/api/companion/ask',json=body).status_code==409 and len(calls)==1

def test_no_consent_stale_question_and_cross_project_are_not_sent(setup):
 c,q,calls=setup;body=grant(c,q)
 assert c.post('/api/companion/ask',json={**body,'confirm':False}).status_code==428
 assert c.post('/api/companion/ask',json={**body,'question':'Different question'}).status_code==409
 assert c.post('/api/companion/preview',json={**q,'project_id':str(uuid4())}).status_code==404
 assert c.post('/api/companion/preview',json={**q,'bug_id':str(uuid4())}).status_code==409
 assert calls==[]

def test_failed_or_other_revision_verification_is_not_marked_verified(setup):
 c,q,calls=setup
 with Session() as db:
  f=db.get(Record,q['fix_id']);f.data={**f.data,'verified':False};db.commit()
 p=c.post('/api/companion/preview',json=q).json();assert p['context']['facts']['patch']['verified'] is False;assert p['context']['facts']['verification'] is None;assert not any(s['page']=='verification' for s in p['sources']);assert calls==[]

def test_provider_failure_never_creates_automatic_second_paid_request(setup,monkeypatch):
 c,q,calls=setup;attempts=[]
 def failed(req):attempts.append(1);return httpx.Response(500,json={'error':{'message':'synthetic failure'}})
 monkeypatch.setattr(chat,'make_adapter',lambda s,audit:AIAdapter(s,transport=httpx.MockTransport(failed),reserve=chat.reserve,audit=audit,sleep=lambda _:None))
 r=c.post('/api/companion/ask',json=grant(c,q));assert r.status_code==503;assert attempts==[1]

def test_unknown_model_and_missing_key_disable_only_contextual_ai(setup,monkeypatch):
 c,q,calls=setup;monkeypatch.delenv('LLM_API_KEY');assert c.get('/api/companion/status').json()['available'] is False
 assert c.post('/api/companion/ask',json=grant(c,q)).status_code==503
 assert c.get('/api/projects').status_code==200
 monkeypatch.setenv('LLM_MODEL','unapproved-provider-model');assert c.post('/api/companion/preview',json=q).status_code==503;assert calls==[]
