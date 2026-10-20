import json
from types import SimpleNamespace
import pytest
from services.ai.engine import Plan,ExtractedRequirement
from services.ai.engine import scenario_schema
from services.ai.validation import (LayeredValidator,SemanticReview,Adjudication,ManualReview,
    check_review,check_adjudication,static_check)
from services.runner.contracts import SandboxJob


def fixture_plan(code='from app import charge\ndef test_charge(): assert charge(2)==2'):
    return Plan.model_validate({'requirements':[{'key':'R1','text':'Charge returns the amount.'}],
        'scenarios':[{'title':'Charge','requirement':'R1','framework':'pytest','gherkin':'Feature: Charge\nScenario: Amount','code':code}]})

EVIDENCE=[ExtractedRequirement(key='R1',text='Charge returns the amount.',source='requirements.md',quote='R1. Charge returns the amount.')]

def review(verdict='supported',rationale='The exact amount is required.'):
    return {'assessments':[{'scenario':0,'verdict':verdict,'requirement_quote':'Charge returns the amount.',
        'assertion_indexes':[0],'rationale':rationale}]}

class Adapter:
    def __init__(self,replies):
        self.replies=iter(replies);self.calls=0;self.seen=[]
        self.settings=SimpleNamespace(output_tokens=4000,max_calls=6)
    def generate(self,operation,model,instruction,context,validate=None):
        self.calls+=1;self.seen.append(context)
        payload=next(self.replies)
        if context.get('schema_style')=='scenarios_only':payload={'scenarios':payload['scenarios']}
        result=model.model_validate(payload)
        return validate(result) if validate else result

def execute(snapshot):
    job=SandboxJob.model_validate(snapshot)
    assert job.phase=='validate'
    return {'status':'completed','runtime':'runsc','image_id':'sha256:'+'a'*64,'snapshot_sha256':job.fingerprint(),
        'validation':{'syntax':True,'discovery':True,'kind':'valid','collected':[{'test_id':str(t.id),'name':'test_charge'} for t in job.tests]}}

def test_technical_and_grounded_semantic_acceptance_without_source_in_review():
    validator=LayeredValidator(execute);adapter=Adapter([review()]);plan=fixture_plan()
    assert validator(plan,[('app.py','def charge(n): return n-1')],EVIDENCE,adapter)==plan
    assert validator.report['status']=='validated'
    assert 'files' not in adapter.seen[0] and 'return n-1' not in json.dumps(adapter.seen)
    assert adapter.settings.output_tokens==4000

def test_false_rejection_needs_independent_grounded_counterargument():
    plan=fixture_plan();first=review('invalid_test','All domain values must be enumerated.')
    second={**review(),'counterarguments':[{'scenario':0,'disputed_claim':'All domain values must be enumerated.',
        'code_quote':'assert charge(2)==2','requirement_quote':'Charge returns the amount.',
        'rationale':'Document specifies the result, not exhaustive enumeration; the assertion checks a valid example.'}]}
    validator=LayeredValidator(execute);adapter=Adapter([first,second])
    assert validator(plan,[('app.py','def charge(n): return n')],EVIDENCE,adapter)==plan
    assert validator.report['classification']=='reviewer_false_rejection'
    assert 'disputed_review' in adapter.seen[1] and 'files' not in adapter.seen[1]
    with pytest.raises(ValueError,match='counterarguments'):
        check_adjudication(Adjudication.model_validate({**review(),'counterarguments':[]}),plan,EVIDENCE,SemanticReview.model_validate(first))

def test_ambiguity_stops_without_accepting_or_changing_test():
    validator=LayeredValidator(execute);plan=fixture_plan();before=plan.model_dump()
    adapter=Adapter([review('ambiguous'),{**review('ambiguous'),'counterarguments':[]}])
    with pytest.raises(ManualReview):validator(plan,[('app.py','def charge(n): return n')],EVIDENCE,adapter)
    assert validator.report['status']=='manual_review_required' and validator.report['repairs']==0
    assert plan.model_dump()==before and adapter.calls==2

@pytest.mark.parametrize('code,kind',[
    ('def test_broken(: pass','syntax_error'),('def test_empty(): pass','invalid_test'),
    ('def test_tautology(): assert True','invalid_test'),
    ('import subprocess\ndef test_exec(): assert subprocess.call(["id"])==0','unsafe_test'),
    ('import pytest\n@pytest.mark.skip\ndef test_skip(): assert charge(2)==2','invalid_test')])
def test_error_categories(code,kind):assert static_check(fixture_plan(code))==kind

def test_no_assertion_or_quote_can_be_omitted():
    plan=fixture_plan('from app import charge\ndef test_charge():\n assert charge(2)==2\n assert charge(3)==3')
    with pytest.raises(ValueError,match='omitted'):check_review(SemanticReview.model_validate(review()),plan,EVIDENCE)
    value=review();value['assessments'][0]['requirement_quote']='Invented error contract'
    with pytest.raises(ValueError,match='ungrounded'):check_review(SemanticReview.model_validate(value),fixture_plan(),EVIDENCE)

def test_syntax_failure_gets_one_repair_before_discovery_and_review():
    bad=fixture_plan('def test_broken(: pass');good=fixture_plan()
    adapter=Adapter([good.model_dump(),review()]);validator=LayeredValidator(execute)
    assert validator(bad,[('app.py','def charge(n): return n')],EVIDENCE,adapter)==good
    assert validator.report['repairs']==1 and validator.report['attempts'][0]['technical_kind']=='syntax_error'

def test_failed_discovery_cannot_be_overruled_by_semantic_approval():
    def broken(snapshot):
        result=execute(snapshot);result['validation'].update(discovery=False,kind='invalid_test',collected=[]);return result
    adapter=Adapter([fixture_plan().model_dump()]);validator=LayeredValidator(broken)
    with pytest.raises(ManualReview):validator(fixture_plan(),[('app.py','def charge(n): return n')],EVIDENCE,adapter)
    assert adapter.calls==1 and all(c['operation']=='repair_tests' for c in adapter.seen)

def test_untrusted_runner_snapshot_cannot_validate_tests():
    def forged(snapshot):
        result=execute(snapshot);result['snapshot_sha256']='0'*64;return result
    validator=LayeredValidator(forged);adapter=Adapter([])
    with pytest.raises(ManualReview):validator(fixture_plan(),[('app.py','def charge(n): return n')],EVIDENCE,adapter)
    assert adapter.calls==0

def test_grounding_uses_original_document_not_only_extractor_excerpt():
    partial=[ExtractedRequirement(key='R1',text='Charge returns the amount.',source='requirements.md',quote='Charge returns')]
    value=SemanticReview.model_validate(review())
    with pytest.raises(ValueError):check_review(value,fixture_plan(),partial)
    assert check_review(value,fixture_plan(),partial,{'requirements.md':'R1. Charge returns the amount.'})==value
    value.assessments[0].requirement_quote='Unspecified authorization rule'
    with pytest.raises(ValueError):check_review(value,fixture_plan(),partial,{'requirements.md':'R1. Charge returns the amount.'})

def test_scenario_schema_never_accepts_changed_requirement_identity_or_framework():
    schema=scenario_schema(fixture_plan().requirements,'pytest')
    payload={'scenarios':fixture_plan().model_dump()['scenarios']}
    assert schema.model_validate(payload).scenarios[0].requirement=='R1'
    payload['scenarios'][0]['requirement']='Charge returns the amount.'
    with pytest.raises(ValueError):schema.model_validate(payload)
    payload['scenarios'][0]['requirement']='R1';payload['scenarios'][0]['framework']='playwright'
    with pytest.raises(ValueError):schema.model_validate(payload)
    payload['scenarios'][0]['framework']='pytest';payload['requirements']=[{'key':'R2','text':'invented'}]
    with pytest.raises(ValueError):schema.model_validate(payload)

def test_operation_output_cap_cannot_increase_user_limit(monkeypatch):
    import httpx
    from pydantic import BaseModel
    from services.ai.adapter import AIAdapter
    monkeypatch.setenv('LLM_API_KEY','unit-cap-key')
    class Reply(BaseModel):value:int
    seen=[];events=[]
    def provider(request):
        body=json.loads(request.content);seen.append(body['max_completion_tokens'])
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"value":1}'}}]})
    adapter=AIAdapter(transport=httpx.MockTransport(provider),audit=events.append)
    adapter.operation_limits={'compact':1000,'larger':9000}
    adapter.generate('compact',Reply,'Return one.',{})
    adapter.generate('larger',Reply,'Return one.',{})
    assert seen==[1000,4000] and adapter.settings.output_tokens==4000
    assert events[0]['reserved_cost_micro_usd']<events[1]['reserved_cost_micro_usd']

def test_runtime_missing_selector_is_not_a_confirmed_product_bug():
    from services.ai.validation import execution_issue
    result={'status':'completed','runtime':'runsc','cases':[{'status':'failed','traceback':'Error: expect(locator) failed: element(s) not found'}]}
    assert execution_issue(result)=='test_binding_ambiguity'
    result['cases'][0]['traceback']='AssertionError: expected total 210 received 202'
    assert execution_issue(result) is None
    result['cases'][0]['status']='skipped'
    assert execution_issue(result)=='invalid_test'
    result.update(status='failed')
    assert execution_issue(result)=='infrastructure_error'
