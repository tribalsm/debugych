import pytest
from services.ai.engine import TestGenerator, TestPlanner, Plan, CodeAnalyzer

def plan_dict():
    return {'requirements':[{'key':'R1','text':'Balance is inclusive'}], 'scenarios':[{'title':'Exact balance','requirement':'R1','gherkin':'Feature: Payment\nScenario: Exact balance\n Given balance is 1\n When pay 1\n Then accepted','code':'def test_exact():\n    assert True\n','framework':'pytest'}]}

def test_missing_key_does_not_send_files(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    with pytest.raises(ValueError, match='LLM_API_KEY'):
        TestGenerator.generate([('app.py','pass')])

def test_context_limit_is_explicit_not_silent_truncation(monkeypatch):
    from services.ai.adapter import AIAdapter
    monkeypatch.setenv('LLM_API_KEY','test-not-a-secret')
    monkeypatch.setenv('LLM_CONTEXT_CHARS','100')
    with pytest.raises(ValueError,match='context_limit'):
        TestGenerator.generate([('requirements.md','R1. '*1000)],AIAdapter())

def test_code_analyzer_parses_without_importing():
    result = CodeAnalyzer.summarize([('danger.py','raise RuntimeError("must not execute")\ndef pay(): pass')])
    assert result[0]['functions'] == [{'name':'pay','line':2}]

def test_generated_python_must_parse():
    plan = plan_dict()
    plan['scenarios'][0]['code'] = 'def broken('
    with pytest.raises(ValueError):
        TestPlanner.validate(Plan(**plan))
