import json
import httpx
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import ai_runtime
from services.ai.adapter import AIAdapter

def grant(client,pid):
    p=client.get(f'/api/projects/{pid}/ai-context').json()
    return {'consent':{'confirm':True,'project_state_sha256':p['project_state_sha256'],'provider_fingerprint':p['provider_fingerprint']}}

def configure(monkeypatch,handler):
    monkeypatch.setenv('LLM_API_KEY','integration-key')
    # Keep real schema validation, privacy, budget and audit; replace HTTP only.
    monkeypatch.setattr(ai_runtime,'AIAdapter',lambda settings,**kw:AIAdapter(settings,transport=httpx.MockTransport(handler),sleep=lambda _:None,**kw))

def project(c):
    pid=c.post('/api/projects',json={'name':'New generation'}).json()['id']
    for name,data in [('app.py',b'def charge(n): return n'),('requirements.md',b'R1. Charge returns the amount.')]:
        assert c.post(f'/api/projects/{pid}/files',files={'file':(name,data)}).status_code==201
    return pid

def test_two_stage_grounding_and_saved_audit(monkeypatch):
    sent=[]
    def provider(request):
        body=json.loads(request.content);value=json.loads(body['messages'][-1]['content']);sent.append(value)
        if value['operation']=='extract_requirements':
            payload={'requirements':[{'key':'R1','text':'Charge returns the amount.','source':'requirements.md','quote':'R1. Charge returns the amount.'}]}
        else:
            payload={'requirements':value['requirements'],'scenarios':[{'title':'Amount','requirement':'R1','framework':'pytest','gherkin':'Feature: Charge\nScenario: Amount\n Given one\n When charged\n Then one','code':'from app import charge\ndef test_charge(): assert charge(1)==1'}]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload)}}]})
    configure(monkeypatch,provider)
    with TestClient(app) as c:
        pid=project(c)
        job=c.post(f'/api/projects/{pid}/analyze',json=grant(c,pid)).json()
        result=c.get('/api/runs/'+job['id']).json()
        assert result['status']=='completed',result
        assert result['requirement_evidence'][0]['source']=='requirements.md'
        assert [v['operation'] for v in sent]==['extract_requirements','generate_tests']
        assert 'files' not in sent[0]
        assert len(c.get(f'/api/projects/{pid}/test-cases').json())==1
        stats=c.get(f'/api/projects/{pid}/ai-statistics').json()
        assert stats['attempts']==stats['succeeded']==2
        assert stats['provider_usage_available']==0 and stats['reserved_tokens']>0

def test_ungrounded_requirements_fail_without_partial_plan(monkeypatch,caplog):
    def provider(request):
        payload={'requirements':[{'key':'R1','text':'invented','source':'requirements.md','quote':'NOT IN DOCUMENT private-sensitive-source'}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(payload)}}]})
    configure(monkeypatch,provider)
    with TestClient(app) as c:
        pid=project(c)
        job=c.post(f'/api/projects/{pid}/analyze',json=grant(c,pid)).json()
        run=c.get('/api/runs/'+job['id']).json()
        assert run['status']=='failed' and 'invalid_structured_response' in run['error']
        assert c.get(f'/api/projects/{pid}/requirements').json()==[]
        assert c.get(f'/api/projects/{pid}/test-cases').json()==[]
        stats=c.get(f'/api/projects/{pid}/ai-statistics').json()
        assert stats['attempts']==stats['failed']==2
        assert 'private-sensitive-source' not in json.dumps(stats) and 'private-sensitive-source' not in caplog.text


def test_uncovered_extracted_requirement_is_retried_and_not_saved(monkeypatch):
    def provider(request):
        value=json.loads(json.loads(request.content)['messages'][-1]['content'])
        if value['operation']=='extract_requirements':
            payload={'requirements':[{'key':'R1','text':'Charge returns the amount.','source':'requirements.md','quote':'R1. Charge returns the amount.'},
                                     {'key':'R2','text':'Reset clears amount.','source':'reset.md','quote':'R2. Reset clears amount.'}]}
        else:
            payload={'requirements':value['requirements'],'scenarios':[{'title':'Amount','requirement':'R1','framework':'pytest','gherkin':'Feature: Charge\nScenario: Amount','code':'def test_amount(): assert True','dimensions':['positive']}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(payload)}}]})
    configure(monkeypatch,provider)
    with TestClient(app) as c:
        pid=project(c)
        c.post(f'/api/projects/{pid}/files',files={'file':('reset.md',b'R2. Reset clears amount.')})
        job=c.post(f'/api/projects/{pid}/analyze',json=grant(c,pid)).json()
        assert c.get('/api/runs/'+job['id']).json()['status']=='failed'
        assert c.get(f'/api/projects/{pid}/test-cases').json()==[]
        stats=c.get(f'/api/projects/{pid}/ai-statistics').json()
        assert stats['attempts']==3 and stats['failed']==2


def test_rejected_review_retains_private_draft_without_executable_plan(monkeypatch,caplog):
    monkeypatch.setenv('LLM_TEST_REVIEW','1')
    monkeypatch.setenv('LLM_MAX_CALLS','6')
    def provider(request):
        value=json.loads(json.loads(request.content)['messages'][-1]['content'])
        if value['operation']=='extract_requirements':
            payload={'requirements':[{'key':'R1','text':'Charge returns the amount.','source':'requirements.md','quote':'R1. Charge returns the amount.'}]}
        elif value['operation']=='review_tests':
            payload={'approved':False,'issues':['private-review-detail: R1 amount assertion is missing']}
        else:
            payload={'requirements':value['requirements'],'scenarios':[{'title':'Amount','requirement':'R1','framework':'pytest',
                'gherkin':'Feature: Charge\nScenario: Amount','code':'def test_amount(): assert True'}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(payload)}}]})
    configure(monkeypatch,provider)
    with TestClient(app) as c:
        pid=project(c)
        job=c.post(f'/api/projects/{pid}/analyze',json=grant(c,pid)).json()
        result=c.get('/api/runs/'+job['id']).json()
        assert result['status']=='failed' and 'test_review_rejected' in result['error']
        assert len(result['generation_review']['drafts'])==2
        assert result['generation_review']['drafts'][0]['review']['issues'][0].startswith('private-review-detail')
        assert c.get(f'/api/projects/{pid}/test-cases').json()==[]
        assert c.get(f'/api/projects/{pid}/requirements').json()==[]
        assert 'private-review-detail' not in caplog.text
        assert 'private-review-detail' not in json.dumps(c.get(f'/api/projects/{pid}/ai-statistics').json())
