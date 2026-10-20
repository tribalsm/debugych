import io
import stat
import zipfile
import pytest
from apps.api.uploads import unpack, validate, valid_name
from services.ai.engine import FailureAnalyzer, VerificationEngine, Plan, TestPlanner

@pytest.mark.parametrize('name', ['../escape.py', '/etc/file.py', 'C:/file.py', 'a\\b.py', '.secret.py', 'a/../../bad.py', 'a\x00.py'])
def test_reject_unsafe_name(name):
    with pytest.raises(ValueError):
        valid_name(name)

def test_text_content():
    assert validate('file.py', b'print(1)') == '.py'
    with pytest.raises(ValueError):
        validate('file.pdf', b'not pdf')
    with pytest.raises(ValueError):
        validate('file.py', b'bad\x00binary')

@pytest.mark.parametrize('symlink', [False, True])
def test_archive_rejects_traversal_and_symlink(symlink):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        item = zipfile.ZipInfo('link.py' if symlink else '../bad.py')
        if symlink:
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(item, 'target.py')
    with pytest.raises(ValueError):
        unpack('source.zip', buf.getvalue())

def test_archive_rejects_excess_entries():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for i in range(101):
            z.writestr(f'{i}.py', 'pass')
    with pytest.raises(ValueError):
        unpack('source.zip', buf.getvalue())

def test_failure_classification_does_not_confirm_infrastructure():
    assert FailureAnalyzer.classify({'status': 'failed', 'traceback': 'ModuleNotFoundError'}, True, True) == 'infrastructure'
    assert FailureAnalyzer.classify({'status': 'failed', 'traceback': 'AssertionError'}) == 'reproduced'
    assert FailureAnalyzer.classify({'status': 'failed', 'traceback': 'AssertionError'}, True, True) == 'confirmed'
    assert FailureAnalyzer.classify({'status': 'failed', 'traceback': "Failed: DID NOT RAISE <class 'ValueError'>"}, True, False) == 'reproduced'
    assert FailureAnalyzer.classify({'status': 'error', 'traceback': 'AssertionError'}, True, True) == 'infrastructure'

def test_verification_requires_original_test_and_all_regression():
    before = {'cases': [{'name': 'bug', 'status': 'failed'}, {'name': 'regression', 'status': 'passed'}]}
    after = {'cases': [{'name': 'regression', 'status': 'passed'}]}
    assessment = VerificationEngine.assess(before, after)
    assert not assessment['original_fixed']
    assert assessment['regressions_absent']
    assert not assessment['full_correctness_proven']

def test_plan_requires_requirement_traceability():
    plan = Plan(requirements=[{'key':'R1','text':'Balance inclusive'}],scenarios=[{'title':'T','requirement':'missing','gherkin':'Feature: X','code':'assert True','framework':'pytest'}])
    with pytest.raises(ValueError):
        TestPlanner.validate(plan)
