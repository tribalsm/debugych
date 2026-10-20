"""Storage/transaction tests with seeded verification metadata, not execution claims."""
from uuid import uuid4
from pathlib import Path
from sqlalchemy import select
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from apps.api.main import app,Approval
from apps.api.db import Session,Project,Record,add_record
from apps.api.jobs import DATA
from apps.api.bug_workflow import prepare_patch,state_hash,digest,apply_uploaded

@pytest.fixture
def seeded():
    with TestClient(app):
        with Session() as db:
            project=Project(name='Transactional apply'); db.add(project); db.flush()
            files=[]; snapshot_files=[]
            for name in ['first.py','second.py']:
                storage=str(uuid4()); (DATA / storage).write_bytes(b'value = 1\n')
                files.append(add_record(db,project.id,'file',{'name':name,'storage':storage,'size':10}))
                snapshot_files.append({'path':name,'content':'value = 1\n'})
            requirement=add_record(db,project.id,'requirement',{'key':'R1','text':'Value is 2'})
            test=add_record(db,project.id,'test',{'title':'Value','code':'def test_value(): assert False','gherkin':'Feature: Value','framework':'pytest','requirement_id':requirement.id})
            snapshot={'id':str(uuid4()),'files':snapshot_files,'tests':[{'id':test.id,'requirement_id':requirement.id,'code':test.data['code']}]}
            original=add_record(db,project.id,'run',{'status':'completed','snapshot':snapshot})
            proof_id=str(uuid4())
            bug=add_record(db,project.id,'bug',{'run_id':original.id,'status':'fix_verified','proof_id':proof_id})
            plan={'explanation':'Set both values','changes':[{'path':f['path'],'before_sha256':digest(f['content']),'content':'value = 2\n'} for f in snapshot_files]}
            fix=add_record(db,project.id,'fix',{**prepare_patch(snapshot,plan),'bug_id':bug.id,'proof_id':proof_id,'verified':True,'applied':False})
            verification=add_record(db,project.id,'run',{'status':'completed','operation':'verify','verified':True,'fix_id':fix.id,'patch_sha256':fix.data['patch_sha256']})
            fix.data={**fix.data,'verification_id':verification.id}
            original.data={**original.data,'project_state_sha256':state_hash(db,project.id)}
            db.commit()
            yield db,bug,fix,files,Approval(confirm=True,fix_id=fix.id,verification_id=verification.id,patch_sha256=fix.data['patch_sha256'])

def test_apply_updates_all_pointers_and_retains_original_blobs(seeded):
    db,bug,fix,files,approval=seeded
    old=[row.data['storage'] for row in files]
    apply_uploaded(db,bug,fix,approval)
    assert fix.data['applied'] and len(fix.data['application']['files'])==2
    assert all((DATA / row.data['storage']).read_text()=='value = 2\n' for row in files)
    assert all((DATA / storage).read_text()=='value = 1\n' for storage in old)

def test_partial_storage_failure_rolls_back_every_file(seeded,monkeypatch):
    db,bug,fix,files,approval=seeded
    old=[row.data['storage'] for row in files]
    blobs=set(DATA.iterdir())
    original=Path.open; calls=[]
    def fault(path,mode='r',*args,**kwargs):
        if mode=='xb':
            calls.append(path)
            if len(calls)==2:raise OSError('Injected disk failure')
        return original(path,mode,*args,**kwargs)
    monkeypatch.setattr(Path,'open',fault)
    with pytest.raises(OSError):apply_uploaded(db,bug,fix,approval)
    assert [row.data['storage'] for row in files]==old
    assert not fix.data['applied']
    assert set(DATA.iterdir())==blobs

def test_stale_test_or_tampered_diff_cannot_be_applied(seeded):
    db,bug,fix,files,approval=seeded
    fix.data={**fix.data,'diff':'tampered'};db.commit()
    with pytest.raises(HTTPException) as error:apply_uploaded(db,bug,fix,approval)
    assert error.value.status_code==409
    assert all((DATA / row.data['storage']).read_text()=='value = 1\n' for row in files)

@pytest.mark.parametrize('kind,key,new',[('test','code','def test_changed(): assert True'),('requirement','text','A different expectation')])
def test_changed_expectation_invalidates_verified_patch(seeded,kind,key,new):
    db,bug,fix,files,approval=seeded
    row=db.scalar(select(Record).where(Record.project_id==bug.project_id,Record.kind==kind))
    row.data={**row.data,key:new}; db.commit()
    with pytest.raises(HTTPException) as error:apply_uploaded(db,bug,fix,approval)
    assert error.value.status_code==409 and not fix.data['applied']
    assert all((DATA / row.data['storage']).read_text()=='value = 1\n' for row in files)

def test_lost_commit_ack_does_not_delete_committed_blobs(seeded,monkeypatch):
    db,bug,fix,files,approval=seeded
    commit=db.commit
    def uncertain():
        commit()
        raise OSError('Simulated lost acknowledgement after DB commit')
    monkeypatch.setattr(db,'commit',uncertain)
    with pytest.raises(OSError):apply_uploaded(db,bug,fix,approval)
    db.refresh(fix)
    assert fix.data['applied']
    assert all((DATA / row.data['storage']).read_text()=='value = 2\n' for row in files)
    assert apply_uploaded(db,bug,fix,approval).data['applied']
