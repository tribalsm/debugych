import json
import httpx
import pytest
from services.ai.adapter import AIError
from services.ai.adapter import AIAdapter
from services.ai.engine import TestGenerator


def test_document_only_review_corrects_new_plan_before_any_execution(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','unit-review-key')
    monkeypatch.setenv('LLM_TEST_REVIEW','1')
    monkeypatch.setenv('LLM_MAX_CALLS','6')
    seen=[];generated=0;reviews=0
    def provider(request):
        nonlocal generated,reviews
        body=json.loads(request.content);context=json.loads(body['messages'][-1]['content']);seen.append(context)
        if context['operation']=='extract_requirements':
            result={'requirements':[{'key':'R1','text':'Charge returns the amount.','source':'requirements.md','quote':'R1. Charge returns the amount.'}]}
        elif context['operation']=='review_tests':
            reviews+=1
            assert 'files' not in context and 'code_structure' not in context
            assert 'return n-1' not in json.dumps(context)
            assert body['max_completion_tokens']==512
            result={'approved':reviews==2,'issues':[] if reviews==2 else ['R1 requires amount 1; expected 0 contradicts the document.']}
        else:
            generated+=1
            result={'requirements':context['requirements'],'scenarios':[{'title':'Charge','requirement':'R1','dimensions':['positive'],
                'gherkin':'Feature: Charge\nScenario: Amount','framework':'pytest',
                'code':'from app import charge\ndef test_charge(): assert charge(1)=='+('0' if generated==1 else '1')}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]})
    events=[]
    adapter=AIAdapter(transport=httpx.MockTransport(provider),audit=events.append)
    plan=TestGenerator.generate([('app.py','def charge(n): return n-1'),('requirements.md','R1. Charge returns the amount.')],adapter)
    assert plan.scenarios[0].code.endswith('==1')
    assert [c['operation'] for c in seen]==['extract_requirements','generate_tests','review_tests','generate_tests','review_tests']
    assert [c['review_approved'] for c in events if c['operation']=='review_tests']==[False,True]
    assert adapter.settings.output_tokens==4000


def test_browser_contract_rejects_unknown_or_missing_requirement(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','unit-review-key')
    monkeypatch.setenv('LLM_TEST_REVIEW','1')
    operations=[]
    def provider(request):
        context=json.loads(json.loads(request.content)['messages'][-1]['content'])
        operations.append(context['operation'])
        if context['operation']=='extract_requirements':
            result={'requirements':[{'key':'R1','text':'Reset restores 3.','source':'requirements.md','quote':'Reset restores 3.'}],
                    'acceptance_contract':{'cases':[{'requirement':'INVENTED','action':'reset','expected':'3'}]}}
        else:pytest.fail('Invalid contract reached code generation')
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]})
    adapter=AIAdapter(transport=httpx.MockTransport(provider),sleep=lambda _:None)
    with pytest.raises(AIError,match='invalid_structured_response'):
        TestGenerator.generate([('widget.tsx','// untrusted'),('requirements.md','Reset restores 3.')],adapter)
    assert operations==['extract_requirements','extract_requirements']
    assert adapter.settings.output_tokens==4000


def test_browser_acceptance_precedes_source_and_survives_review(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','unit-review-key')
    monkeypatch.setenv('LLM_TEST_REVIEW','1')
    seen=[]
    requirement={'key':'R1','text':'Reset restores quantity 3.'}
    contract={'cases':[{'requirement':'R1','action':'Change quantity then reset','expected':'Quantity is 3'}]}
    def provider(request):
        body=json.loads(request.content);context=json.loads(body['messages'][-1]['content']);seen.append(context)
        operation=context['operation']
        if operation=='extract_requirements':
            assert set(context)=={'operation','documents'}
            assert 'setQuantity(9)' not in json.dumps(context)
            result={'requirements':[{**requirement,'source':'requirements.md','quote':requirement['text']}],
                    'acceptance_contract':contract}
        elif operation=='generate_tests':
            assert context['acceptance_contract']==contract
            assert context['files'][0]['content']=='setQuantity(9)'
            result={'requirements':[requirement],'scenarios':[{'title':'Reset','requirement':'R1',
                'gherkin':'Feature: Reset\nScenario: Restore quantity','framework':'playwright',
                'code':'test("restore quantity", async ({page}) => { await expect(page.getByLabel("Quantity")).toHaveValue("3"); });'}]}
        else:
            assert context['acceptance_contract']==contract
            assert 'files' not in context
            result={'approved':True,'issues':[]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]})
    adapter=AIAdapter(transport=httpx.MockTransport(provider))
    plan=TestGenerator.generate([('widget.tsx','setQuantity(9)'),('requirements.md',requirement['text'])],adapter)
    assert [c['operation'] for c in seen]==['extract_requirements','generate_tests','review_tests']
    assert 'toHaveValue("3")' in plan.scenarios[0].code
    assert adapter.settings.output_tokens==4000
    assert adapter.acceptance_contract==contract
    assert adapter.review_drafts[0]['review']=={'approved':True,'issues':[]}


def test_failure_excerpt_retains_expected_actual_without_repeated_call_log():
    from apps.api.bug_workflow import failure_excerpt
    raw='Error: expect(locator).toHaveText(expected) failed\nExpected: 0\nReceived: 2\nCall log:\n'+'retry\n'*500
    value=failure_excerpt(raw)
    assert 'Expected: 0' in value['diagnostic_excerpt'] and 'Received: 2' in value['diagnostic_excerpt']
    assert 'retry' not in value['diagnostic_excerpt'] and value['excerpted']
    assert value['full_traceback_chars']==len(raw)
    assert failure_excerpt('short Python assertion')['excerpted'] is False
    assert len(failure_excerpt('x'*5000)['diagnostic_excerpt'])<1250
