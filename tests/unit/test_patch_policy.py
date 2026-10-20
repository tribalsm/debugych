from uuid import uuid4
import pytest
from apps.api.bug_workflow import prepare_patch,digest,case_map

def snapshot(path='calc.py',content='def add(a,b): return a-b\n'):
    return {'id':str(uuid4()),'files':[{'path':path,'content':content}],
            'tests':[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':'def test_add(): assert False'}]}

def plan(snap,path=None,after='def add(a,b): return a+b\n'):
    source=snap['files'][0]
    return {'explanation':'Fix addition','changes':[{'path':path or source['path'],'before_sha256':digest(source['content']),'content':after}]}

def test_diff_derived_from_exact_contents_and_fingerprint():
    snap=snapshot()
    fix=prepare_patch(snap,plan(snap))
    assert '-def add(a,b): return a-b' in fix['diff'] and '+def add(a,b): return a+b' in fix['diff']
    assert len(fix['patch_sha256'])==64
    assert snap['files'][0]['content']=='def add(a,b): return a-b\n'

@pytest.mark.parametrize('path',['../outside.py','new.py','tests/a.py','test_calc.py','conftest.py','coverage.py','source_test.py'])
def test_cannot_modify_tests_infrastructure_or_create_paths(path):
    snap=snapshot(path if path!='new.py' else 'calc.py')
    with pytest.raises(ValueError):prepare_patch(snap,plan(snap,path))

def test_reject_hash_mismatch_noop_and_invalid_python():
    snap=snapshot()
    value=plan(snap);value['changes'][0]['before_sha256']='0'*64
    with pytest.raises(ValueError):prepare_patch(snap,value)
    with pytest.raises(ValueError):prepare_patch(snap,plan(snap,after=snap['files'][0]['content']))
    with pytest.raises(ValueError):prepare_patch(snap,plan(snap,after='def broken('))

def test_no_newline_diff_remains_valid():
    snap=snapshot(content='value = 1')
    fix=prepare_patch(snap,plan(snap,after='value = 2'))
    assert '-value = 1\n\\ No newline at end of file\n+value = 2\n' in fix['diff']

def test_proof_rejects_skips_errors_and_duplicate_case_ids():
    case={'name':'test_x','test_id':str(uuid4()),'status':'passed','classname':'module'}
    for cases in [[case,case],[{**case,'status':'error'}],[{**case,'status':'failed','traceback':'ModuleNotFoundError'}],[{**case,'status':'skipped'}],[]]:
        with pytest.raises(ValueError):case_map({'status':'completed','runtime':'runsc','cases':cases})

def test_classes_are_distinct_case_identities():
    case={'name':'test_x','test_id':str(uuid4()),'status':'passed'}
    assert len(case_map({'status':'completed','runtime':'runsc','cases':[{**case,'classname':'A'},{**case,'classname':'B'}]}))==2
