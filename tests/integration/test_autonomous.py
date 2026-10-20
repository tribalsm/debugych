"""Actual API/DB/adapter with mocked external HTTP and isolated runner transport."""
import hashlib,json
import httpx
from fastapi.testclient import TestClient
from apps.api import ai_runtime,main,sandbox_client
from apps.api.main import app
from services.ai.adapter import AIAdapter
from services.runner.contracts import SandboxJob

def setup(monkeypatch,ambiguous=False):
    monkeypatch.setenv('LLM_API_KEY','autonomous-integration-key')
    monkeypatch.setenv('LLM_MAX_CALLS','6');monkeypatch.setenv('SANDBOX_ENABLED','1')
    monkeypatch.setattr(main,'sandbox_health',lambda:{'runtime':'runsc','playwright_image_id':'sha256:'+'a'*64})
    calls=[]
    def provider(request):
        c=json.loads(json.loads(request.content)['messages'][-1]['content']);calls.append(c['operation'])
        if c['operation']=='extract_requirements':
            result={'requirements':[{'key':'R1','text':'Charge returns the amount.','source':'requirements.md','quote':'R1. Charge returns the amount.'}]}
        elif c['operation']=='generate_tests':
            result={'requirements':c['requirements'],'scenarios':[{'title':'Charge','requirement':'R1','framework':'pytest',
                'gherkin':'Feature: Charge\nScenario: Amount','code':'from app import charge\ndef test_charge(): assert charge(2)==2'}]}
        elif c['operation'] in ('validate_semantics','adjudicate_semantics'):
            result={'assessments':[{'scenario':0,'verdict':'ambiguous' if ambiguous else 'supported',
                'requirement_quote':'Charge returns the amount.','assertion_indexes':[0],'rationale':'Public R1 specifies the supplied amount.'}]}
            if c['operation']=='adjudicate_semantics':result['counterarguments']=[]
            assert 'files' not in c and 'return n-1' not in json.dumps(c)
        else:
            assert c['operation']=='fix'
            source=next(f for f in c['files'] if f['path']=='app.py')
            result={'explanation':'Return the documented amount.','changes':[{'path':'app.py','before_sha256':source['sha256'],'content':'def charge(n): return n\n'}]}
        if c.get('schema_style')=='scenarios_only':result={'scenarios':result['scenarios']}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]})
    monkeypatch.setattr(ai_runtime,'AIAdapter',lambda settings,**kw:AIAdapter(settings,transport=httpx.MockTransport(provider),sleep=lambda _:None,**kw))
    def runner(snapshot):
        job=SandboxJob.model_validate(snapshot)
        result={'status':'completed','runtime':'runsc','image_id':'sha256:'+'a'*64,'snapshot_sha256':job.fingerprint(),'cases':[],'passed':0,'failed':0,'errors':0,'skipped':0,'artifacts':[]}
        if job.phase=='validate':
            result['validation']={'syntax':True,'discovery':True,'kind':'valid','collected':[{'test_id':str(t.id),'name':'test_charge'} for t in job.tests]}
        else:
            buggy='return n-1' in job.files[0].content
            result['cases']=[{'test_id':str(t.id),'classname':'tests','name':'test_charge','status':'failed' if buggy else 'passed','traceback':'AssertionError: expected 2 received 1' if buggy else ''} for t in job.tests]
            result['failed' if buggy else 'passed']=len(job.tests)
        return result
    monkeypatch.setattr(sandbox_client,'execute',runner)
    return calls

def start(c):
    pid=c.post('/api/projects',json={'name':'Unseen autonomous input'}).json()['id']
    c.post(f'/api/projects/{pid}/files',files={'file':('app.py',b'def charge(n): return n-1\n')})
    c.post(f'/api/projects/{pid}/files',files={'file':('requirements.md',b'R1. Charge returns the amount.')})
    manifest=c.get(f'/api/projects/{pid}/ai-context').json()
    consent={'confirm':True,'project_state_sha256':manifest['project_state_sha256'],'provider_fingerprint':manifest['provider_fingerprint']}
    job=c.post(f'/api/projects/{pid}/autonomous',json={'consent':consent})
    assert job.status_code==202,job.text
    return pid,c.get('/api/runs/'+job.json()['id']).json()

def test_autonomous_workflow_requires_no_review_override_and_never_applies(monkeypatch):
    calls=setup(monkeypatch)
    with TestClient(app) as c:
        pid,result=start(c)
        assert result['status']=='completed',result
        assert result['qa_report']['autonomous'] and result['qa_report']['manual_interventions']==0
        assert result['qa_report']['llm_calls']==4 and result['verified']
        assert calls==['extract_requirements','generate_tests','validate_semantics','fix']
        bug=c.get('/api/bugs/'+result['bug_id']).json()
        assert bug['review']['review_kind']=='automated_validation'
        assert 'пользователем' not in bug['confirmation_basis']
        assert c.post('/api/bugs/'+bug['id']+'/apply-fix',json={'confirm':False}).status_code==409
        fix=c.get(f'/api/projects/{pid}/fixes').json()[0]
        assert fix['verified'] and not fix['applied']
        tests=c.get(f'/api/projects/{pid}/test-cases').json()
        assert tests[0]['code']=='from app import charge\ndef test_charge(): assert charge(2)==2'

def test_ambiguous_requirement_never_persists_executable_tests_or_proof(monkeypatch):
    setup(monkeypatch,ambiguous=True)
    with TestClient(app) as c:
        pid,result=start(c)
        assert result['status']=='manual_review_required',result
        assert result['qa_report']['autonomous'] is False
        assert c.get(f'/api/projects/{pid}/test-cases').json()==[]
        assert c.get('/api/bugs?project_id='+pid).json()==[]
