"""Exercise the final scenario-only wire protocol without external requests."""
import json

import httpx
import pytest

from services.ai.adapter import AIAdapter, AIError
from services.ai.engine import Plan, Requirement, TestPlanner, scenario_schema


@pytest.mark.parametrize('framework', ['pytest', 'playwright'])
@pytest.mark.parametrize('broken', ['malformed_json', 'changed_key', 'echoed_requirements'])
def test_scenario_protocol_retries_strictly_and_preserves_framework(monkeypatch, framework, broken):
    monkeypatch.setenv('LLM_API_KEY', 'offline-protocol-key')
    monkeypatch.setenv('LLM_RESPONSE_FORMAT', 'json_object')
    monkeypatch.setenv('LLM_MAX_CALLS', '2')
    requirements = [Requirement(key='R1', text='The result is two.')]
    schema = scenario_schema(requirements, framework)
    payload = {'scenarios': [{'title': 'Result', 'requirement': 'R1', 'framework': framework,
        'gherkin': 'Feature: Result\nScenario: Two\nGiven valid input\nWhen evaluated\nThen the result is two',
        'code': 'def test_result(): assert result()==2' if framework == 'pytest' else
            "import {test,expect} from '@playwright/test';test('result',async()=>{expect(result()).toBe(2)});"}]}
    bad = json.loads(json.dumps(payload))
    if broken == 'changed_key': bad['scenarios'][0]['requirement'] = 'R99'
    if broken == 'echoed_requirements': bad['requirements'] = [r.model_dump() for r in requirements]
    raw = '{invalid JSON' if broken == 'malformed_json' else json.dumps(bad)
    bodies, events = [], []

    def provider(request):
        bodies.append(json.loads(request.content))
        content = raw if len(bodies) == 1 else json.dumps(payload)
        return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})

    adapter = AIAdapter(transport=httpx.MockTransport(provider), audit=events.append, sleep=lambda _: None)
    value = adapter.generate('generate_tests', schema, 'Return JSON scenarios.', {})
    plan = Plan(requirements=requirements, scenarios=[s.model_dump() for s in value.scenarios])
    assert TestPlanner.validate(plan, require_all=True) == plan
    assert len(bodies) == 2 and events[0]['outcome'] != 'succeeded' and events[1]['outcome'] == 'succeeded'
    assert events[0]['validation_reason'].startswith('schema:')
    assert plan.scenarios[0].framework == framework and plan.requirements == requirements
    assert all('schema' in b['messages'][0]['content'] for b in bodies)


def test_persistently_invalid_protocol_never_returns_a_plan(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'offline-protocol-key')
    monkeypatch.setenv('LLM_MAX_CALLS', '2')
    events = []
    adapter = AIAdapter(transport=httpx.MockTransport(lambda _: httpx.Response(200,
        json={'choices': [{'message': {'content': '{"scenarios":[]}'}}]})), audit=events.append, sleep=lambda _: None)
    with pytest.raises(AIError, match='invalid_structured_response'):
        adapter.generate('generate_tests', scenario_schema([Requirement(key='R1', text='Required')], 'pytest'), 'JSON', {})
    assert len(events) == 2 and all(e['outcome'] != 'succeeded' for e in events)


@pytest.mark.parametrize('index', ['0', True, 0.0])
def test_review_json_does_not_coerce_non_integer_indexes(monkeypatch, index):
    from services.ai.validation import SemanticReview
    monkeypatch.setenv('LLM_API_KEY', 'offline-protocol-key')
    monkeypatch.setenv('LLM_MAX_CALLS', '2')
    payload = {'assessments': [{'scenario': index, 'verdict': 'supported',
        'requirement_quote': 'The result is two.', 'assertion_indexes': [0], 'rationale': 'Documented.'}]}
    events = []
    adapter = AIAdapter(transport=httpx.MockTransport(lambda _: httpx.Response(200,
        json={'choices': [{'message': {'content': json.dumps(payload)}}]})), audit=events.append, sleep=lambda _: None)
    with pytest.raises(AIError, match='invalid_structured_response'):
        adapter.generate('validate_semantics', SemanticReview, 'JSON', {})
    assert len(events) == 2 and all(e['outcome'] != 'succeeded' for e in events)
