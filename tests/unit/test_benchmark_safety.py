"""Evaluator tests use data only; project code is never imported or executed."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest


@pytest.fixture
def evaluator(monkeypatch):
    folder=Path(__file__).resolve().parents[1]/'compose'
    monkeypatch.syspath_prepend(str(folder))
    spec=importlib.util.spec_from_file_location('independent_evaluator',folder/'benchmark.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_live_requires_explicit_transport_consent(evaluator,monkeypatch):
    monkeypatch.setattr(evaluator,'request',lambda _: {'ai_available':True,'ai_provider_mode':'live'})
    monkeypatch.setattr(sys,'argv',['benchmark.py'])
    monkeypatch.setattr(evaluator,'evaluate',lambda *args:pytest.fail('Must not send sources'))
    with pytest.raises(SystemExit,match='allow-external'):evaluator.main()


def test_missing_key_writes_honest_report_without_contract_fallback(evaluator,monkeypatch,tmp_path):
    output=tmp_path/'live.json'
    monkeypatch.setattr(evaluator,'request',lambda _: {'ai_available':False,'ai_provider_mode':'live'})
    monkeypatch.setattr(sys,'argv',['benchmark.py','--allow-external','--output',str(output)])
    monkeypatch.setattr(evaluator,'evaluate',lambda *args:pytest.fail('No provider must be invoked'))
    evaluator.main()
    report=json.loads(output.read_text(encoding='utf-8'))
    assert report['status']=='NOT_VERIFIED_API_KEY_MISSING'
    assert report['results']==[] and not report['live_llm_verified']


def test_oracle_control_rejects_partial_skipped_duplicate_and_failed_runs(evaluator):
    run={'status':'completed','runtime':'runsc','cases':[
        {'test_id':'o','classname':'private','name':str(i),'status':'failed' if i==0 else 'passed'} for i in range(4)]}
    assert evaluator.oracle_matches(run,3,1)
    assert not evaluator.oracle_matches({**run,'status':'failed'},3,1)
    assert not evaluator.oracle_matches({**run,'cases':run['cases'][:1]},3,1)
    assert not evaluator.oracle_matches({**run,'cases':run['cases']+[run['cases'][0]]},3,1)
    run['cases'][1]['status']='skipped'
    assert not evaluator.oracle_matches(run,3,1)


def test_private_transform_is_fail_closed_and_does_not_mutate_input(evaluator):
    original=[{'path':'app.py','content':'value=1'}]
    fixed=evaluator.replace(original,[['app.py','value=1','value=2']])
    assert fixed[0]['content']=='value=2' and original[0]['content']=='value=1'
    with pytest.raises(ValueError,match='drift'):evaluator.replace(original,[['app.py','absent','replacement']])


def test_resume_keeps_contract_label_and_never_invokes_generation(evaluator,monkeypatch,tmp_path):
    previous=tmp_path/'before.json';output=tmp_path/'after.json'
    previous.write_text(json.dumps({'provider_mode':'contract-test','status':'CONTRACT_INFRASTRUCTURE_ONLY',
                                   'results':[{'name':'python_dispatch'}]}),encoding='utf-8')
    monkeypatch.setattr(evaluator,'request',lambda _: {'ai_available':False,'ai_provider_mode':'live'})
    monkeypatch.setattr(evaluator,'resume_project',lambda p:{**p,'benchmark':{}})
    monkeypatch.setattr(evaluator,'evaluate',lambda *args:pytest.fail('Resume must not generate'))
    monkeypatch.setattr(sys,'argv',['benchmark.py','--resume-report',str(previous),'--output',str(output)])
    evaluator.main()
    report=json.loads(output.read_text(encoding='utf-8'))
    assert report['provider_mode']=='contract-test' and not report['live_llm_verified']


def test_resume_reads_proof_and_rejected_patch_without_approving(evaluator,monkeypatch):
    calls=[]
    def read(path):
        calls.append(path)
        if path.endswith('/runs'):return [{'operation':'confirm_proof','status':'completed','review':{'run_id':'original'},'replay':{'cases':[]}}]
        if path.endswith('/fixes'):return [{'id':'fix','run_id':'original','verified':False}]
        if path.endswith('/ai-statistics'):return {'attempts':3}
        pytest.fail('Unexpected request')
    monkeypatch.setattr(evaluator,'request',read)
    monkeypatch.setattr(evaluator,'independent',lambda _: {'evaluation':'data only'})
    result=evaluator.resume_project({'name':'python_dispatch','project_id':'p','original':{'id':'original'}})
    assert result['candidates'][0]['verified'] is False
    assert result['proof_replay']=={'cases':[]}
    assert not any('apply' in p or 'propose' in p or 'confirm' in p for p in calls)
