from uuid import uuid4
import pytest
from pydantic import ValidationError
from services.runner.contracts import SandboxJob, SourceFile, SandboxResult

def job(**overrides):
    return {'id':str(uuid4()),'files':[{'path':'pkg/calc.py','content':'def add(a,b): return a+b'}],
            'tests':[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':'def test_one(): assert True'}],**overrides}

@pytest.mark.parametrize('path',['../escape.py','/tmp/x.py','a/../../x.py','a\\x.py','C:/x.py','.hidden.py','x.py/../a.py','x/./y.py','x//y.py','x.exe'])
def test_supervisor_rejects_unsafe_paths(path):
    with pytest.raises(ValidationError):
        SourceFile(path=path,content='pass')

@pytest.mark.parametrize('option',['command','image','volumes','runtime','network_mode','privileged','environment'])
def test_cannot_request_docker_options(option):
    with pytest.raises(ValidationError):
        SandboxJob.model_validate(job(**{option:'unsafe'}))

def test_duplicate_paths_and_snapshot_limit():
    with pytest.raises(ValidationError):
        SandboxJob.model_validate(job(files=[{'path':'calc.py','content':'pass'},{'path':'CALC.py','content':'pass'}]))
    with pytest.raises(ValidationError):
        SandboxJob.model_validate(job(files=[{'path':f'f{i}.py','content':'a'*300000} for i in range(8)]))

def test_snapshot_hash_covers_source_and_tests():
    first=SandboxJob.model_validate(job())
    second=first.model_copy(deep=True)
    second.files[0].content='def add(a,b): return a-b'
    assert first.fingerprint()!=second.fingerprint()
    second=first.model_copy(deep=True)
    second.tests[0].code='def test_two(): assert False'
    assert first.fingerprint()!=second.fingerprint()

def test_untrusted_result_validates_metrics():
    with pytest.raises(ValidationError):
        SandboxResult.model_validate({'status':'completed','cases':[],'passed':-1})
