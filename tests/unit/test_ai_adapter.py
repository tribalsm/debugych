import json
import logging
import httpx
import pytest
from pydantic import BaseModel,ConfigDict
from services.ai.adapter import AIAdapter,AIError,Settings,strict_schema
from services.ai.privacy import sanitize_files,redact

class Result(BaseModel):
    model_config=ConfigDict(extra='forbid')
    answer: str


def test_balance_error_is_not_retried_or_leaked(monkeypatch,caplog):
    events=[]
    client=adapter(monkeypatch,lambda _:httpx.Response(429,json={'error':{'code':'insufficient_quota','message':'PRIVATE SOURCE'}}),audit=events.append)
    with pytest.raises(AIError,match='балансе'):client.generate('probe',Result,'JSON',{})
    assert len(events)==1 and events[0]['provider_failure']=='balance'
    assert 'PRIVATE SOURCE' not in json.dumps(events)+caplog.text


def test_unexpected_response_model_is_rejected(monkeypatch):
    events=[]
    client=adapter(monkeypatch,lambda _:httpx.Response(200,json={**reply(),'model':'other-vendor-model'}),audit=events.append)
    with pytest.raises(AIError,match='provider_model_mismatch'):client.generate('probe',Result,'JSON',{})
    assert events[0]['response_model']=='other-vendor-model'


def test_optional_reasoning_keeps_selected_model_and_schema(monkeypatch):
    monkeypatch.setenv('LLM_REASONING_EFFORT','none')
    bodies=[]
    def provider(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200,json=reply())
    client=adapter(monkeypatch,provider)
    client.generate('probe',Result,'Return JSON',{})
    assert bodies[0]['reasoning_effort']=='none' and bodies[0]['model']==client.settings.model
    assert bodies[0]['response_format']['json_schema']['strict']
    assert 'additionalProperties' in bodies[0]['messages'][0]['content']


def test_echoed_api_key_is_rejected_before_saving_or_execution(monkeypatch,caplog):
    events=[]
    def provider(request):
        return httpx.Response(200,json=reply({'answer':request.headers['authorization'].removeprefix('Bearer ')}))
    client=adapter(monkeypatch,provider,audit=events.append)
    with pytest.raises(AIError,match='sensitive_provider_response'):client.generate('probe',Result,'Return JSON',{})
    assert len(events)==1 and client.settings.key not in json.dumps(events)+caplog.text

def reply(payload=None,**change):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload or {'answer':'ok'}),**change}}]}

def adapter(monkeypatch,handler,**options):
    monkeypatch.setenv('LLM_API_KEY','sk-private-test-key-123456789')
    return AIAdapter(transport=httpx.MockTransport(handler),sleep=lambda seconds:None,**options)

def test_real_http_shape_strict_schema_redaction_and_usage(monkeypatch,caplog):
    events=[];captured=[]
    def handler(request):
        captured.append(json.loads(request.content))
        assert request.headers['authorization'].startswith('Bearer ')
        return httpx.Response(200,json={**reply(),'usage':{'prompt_tokens':21,'completion_tokens':4}})
    client=adapter(monkeypatch,handler,audit=events.append)
    with caplog.at_level(logging.INFO):
        assert client.generate('probe',Result,'Return result',{'source':'API_KEY="customer-sensitive-token"','key':client.settings.key}).answer=='ok'
    body=captured[0]
    assert body['response_format']['json_schema']['strict']
    assert body['response_format']['json_schema']['schema']['additionalProperties'] is False
    assert 'customer-sensitive-token' not in json.dumps(body)
    assert client.settings.key not in json.dumps(body)
    assert client.settings.key not in caplog.text
    assert 'customer-sensitive-token' not in caplog.text
    assert events[0]['usage']=={'prompt_tokens':21,'completion_tokens':4}

@pytest.mark.parametrize('status,expected',[(401,1),(400,1),(429,2),(500,2),(503,2)])
def test_http_retry_policy(monkeypatch,status,expected):
    events=[];calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(status,json={'error':{'message':'must never be logged PRIVATE SOURCE'}},headers={'retry-after':'0'})
    client=adapter(monkeypatch,handler,audit=events.append)
    with pytest.raises(AIError,match='provider_http'):client.generate('probe',Result,'JSON',{})
    assert len(calls)==expected and len(events)==expected
    assert 'PRIVATE SOURCE' not in str(events)

def test_invalid_json_then_valid_with_accurate_attempts(monkeypatch):
    events=[];requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json=reply({'wrong':'field'}) if len(requests)==1 else reply())
    client=adapter(monkeypatch,handler,audit=events.append)
    assert client.generate('probe',Result,'Return JSON',{}).answer=='ok'
    assert [e['outcome'] for e in events]==['failed','succeeded']
    assert events[0]['error_code']=='invalid_structured_response'
    assert events[0]['validation_reason']=='schema:extra_forbidden,missing'
    assert 'schema:extra_forbidden,missing' in requests[1]['messages'][0]['content']
    assert all(e['usage'] is None for e in events)

@pytest.mark.parametrize('body',[[],{'choices':[]},{'choices':[{'message':None}]}])
def test_invalid_envelope_is_validated_and_bounded(monkeypatch,body):
    events=[]
    client=adapter(monkeypatch,lambda r:httpx.Response(200,json=body),audit=events.append)
    with pytest.raises(AIError,match='invalid_structured_response'):client.generate('probe',Result,'JSON',{})
    assert len(events)==2

def test_timeout_retry_and_request_budget(monkeypatch):
    count=[]
    def handler(request):count.append(1);raise httpx.ReadTimeout('private body must not escape',request=request)
    client=adapter(monkeypatch,handler)
    with pytest.raises(AIError,match='provider_transport_temporary'):client.generate('probe',Result,'Return JSON',{})
    assert len(count)==2
    monkeypatch.setenv('LLM_MAX_CALLS','1')
    client=adapter(monkeypatch,handler)
    with pytest.raises(AIError,match='job_budget_exhausted'):client.generate('probe',Result,'Return JSON',{})

@pytest.mark.parametrize('change,code',[({'refusal':'no'},'provider_refusal')])
def test_refusal_is_not_a_plan(monkeypatch,change,code):
    events=[]
    client=adapter(monkeypatch,lambda r:httpx.Response(200,json=reply(**change)),audit=events.append)
    with pytest.raises(AIError,match=code):client.generate('probe',Result,'Return JSON',{})
    assert len(events)==1

def test_truncation_and_oversize_are_not_valid_results(monkeypatch):
    body=reply();body['choices'][0]['finish_reason']='length'
    client=adapter(monkeypatch,lambda r:httpx.Response(200,json=body))
    with pytest.raises(AIError,match='incomplete_response'):client.generate('probe',Result,'JSON',{})
    client=adapter(monkeypatch,lambda r:httpx.Response(200,content=b'x'*1000001))
    with pytest.raises(AIError,match='response_too_large'):client.generate('probe',Result,'JSON',{})

def test_missing_key_and_bad_endpoint_never_connect(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    with pytest.raises(AIError,match='missing_LLM_API_KEY'):AIAdapter().generate('probe',Result,'JSON',{})
    monkeypatch.setenv('LLM_BASE_URL','https://user:secret@example.com/v1?token=secret')
    with pytest.raises(AIError,match='invalid_configuration'):Settings.load()

@pytest.mark.parametrize('name,value',[('LLM_MAX_JOB_TOKENS','1'),('LLM_MAX_JOB_USD','0.000001')])
def test_token_and_cost_admission_precedes_network(monkeypatch,name,value):
    monkeypatch.setenv(name,value)
    calls=[]
    client=adapter(monkeypatch,lambda r:calls.append(r))
    with pytest.raises(AIError,match='job_budget_exhausted'):client.generate('probe',Result,'JSON',{})
    assert calls==[]

def test_explicit_legacy_json_mode_still_validates_schema(monkeypatch):
    monkeypatch.setenv('LLM_RESPONSE_FORMAT','json_object')
    bodies=[]
    def handler(request):
        bodies.append(json.loads(request.content));return httpx.Response(200,json=reply())
    client=adapter(monkeypatch,handler)
    assert client.generate('probe',Result,'JSON',{}).answer=='ok'
    assert bodies[0]['response_format']=={'type':'json_object'}
    assert 'schema' in bodies[0]['messages'][0]['content']

def test_secret_files_and_embedded_credentials_withheld():
    files,manifest=sanitize_files([('.env','API_KEY=abc'),('oracles/answer.md','hidden'),('app.py','password = "very-private"\nurl="postgres://user:pass@host/db"'),('requirements.md','Expected result')])
    assert len(files)==2 and manifest[0]['excluded'] and manifest[1]['excluded']
    assert 'very-private' not in str(files) and 'user:pass' not in str(files)
    assert redact('-----BEGIN PRIVATE KEY-----\nsecret bytes\n-----END PRIVATE KEY-----')[1]==1
    assert 'secret bytes' not in redact('-----BEGIN PRIVATE KEY-----\nsecret bytes')[0]
    assert redact('a'*300000)==('a'*300000,0)

def test_ambiguous_playwright_selector_is_not_product_proof():
    from services.ai.engine import FailureAnalyzer
    assert FailureAnalyzer.classify({'status':'failed','traceback':'Error: expect(locator).toHaveText failed; strict mode violation'},True)=='infrastructure'
