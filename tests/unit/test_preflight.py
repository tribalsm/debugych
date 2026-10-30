import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('preflight',Path('scripts/preflight.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def fixture(info=None,version='2.24.4',config=0,own=False):
    import json
    calls=[]
    def run(args):
        calls.append(args)
        if args[1]=='info':return 0,json.dumps(info if info is not None else {'OSType':'linux','Runtimes':{'runsc':{}}})
        if args[1:3]==['compose','version']:return 0,version
        if args[1]=='compose':return config,''
        if args[1]=='ps':return 0,'a'*12 if own else ''
        if args[1]=='inspect':return 0,json.dumps({'8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8000'}]})
        raise AssertionError('Unexpected command')
    return run,calls

def test_clean_linux_runtime_and_config_are_admitted_without_writes():
    run,calls=fixture();result=module.inspect_environment(run=run,is_occupied=lambda port:False)
    assert result['ready']
    assert all(args[1] in ('info','compose','ps','inspect') for args in calls)
    assert all('config' not in args or args[-1]=='--quiet' for args in calls)

def test_no_fallback_for_missing_runsc_or_windows_containers():
    for info in [{'OSType':'linux','Runtimes':{'runc':{}}},{'OSType':'windows','Runtimes':{'runsc':{}}}]:
        run,_=fixture(info);assert not module.inspect_environment(run=run,is_occupied=lambda p:False)['ready']

def test_foreign_ports_block_but_this_project_can_be_started_again():
    run,_=fixture();assert not module.inspect_environment(run=run,is_occupied=lambda p:p==8000)['ready']
    run,_=fixture(own=True);assert module.inspect_environment(run=run,is_occupied=lambda p:p==8000)['ready']

def test_unavailable_docker_old_compose_and_invalid_config_fail_closed():
    assert not module.inspect_environment(run=lambda args:(-1,'private diagnostic'),is_occupied=lambda p:False)['ready']
    for options in [{'version':'2.23.0'},{'config':1},{'version':'not-json-or-version'}]:
        run,_=fixture(**options);assert not module.inspect_environment(run=run,is_occupied=lambda p:False)['ready']

def test_docker_details_are_not_exposed_and_invalid_project_is_not_executed():
    import pytest
    run,calls=fixture({'OSType':'linux','Runtimes':{'runsc':{}},'secret':'never-log-this'})
    assert 'never-log-this' not in str(module.inspect_environment(run=run,is_occupied=lambda p:False))
    before=len(calls)
    with pytest.raises(ValueError):module.inspect_environment(project='../../another-project',run=run)
    assert len(calls)==before
