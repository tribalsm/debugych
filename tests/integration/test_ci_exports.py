import io
import json
import xml.etree.ElementTree as ET
import zipfile
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from apps.api.ci_exports import junit, export_ci
from apps.api.ci_client import Client, package
from apps.api.main import app
from apps.api.db import Session, add_record


def result(**extra):
    return {'operation':'run','status':'completed','runtime':'runsc','passed':1,'failed':1,'errors':1,'skipped':1,'cases':[
        {'name':'safe <name> & "quoted"\x00','status':'passed','duration':.1},
        {'name':'assertion','status':'failed','traceback':'assert <x>\x01','duration':.2},
        {'name':'fixture','status':'error','traceback':'exception','duration':.3},
        {'name':'skip','status':'skipped','duration':0}],**extra}


def test_junit_counts_escaping_and_failure_types():
    report=ET.fromstring(junit(result()))
    assert report.attrib['tests']=='4' and report.attrib['failures']=='1' and report.attrib['errors']=='1'
    assert report.find('.//testcase').attrib['name']=='safe <name> & "quoted"'
    assert len(report.findall('.//failure'))==len(report.findall('.//error'))==len(report.findall('.//skipped'))==1


@pytest.mark.parametrize('extra',[{'status':'failed'},{'passed':9},{'cases':[],'passed':0,'failed':0,'errors':0,'skipped':0}])
def test_missing_inconsistent_or_crashed_reports_cannot_export_green(extra):
    assert int(ET.fromstring(junit(result(**extra))).attrib['errors'])>0


def test_verify_is_regression_only_and_incomplete_is_rejected():
    report=ET.fromstring(junit({'operation':'verify','status':'completed','baseline':result(),'regression':result(passed=1,failed=0,errors=0,skipped=0,cases=[{'name':'fixed','status':'passed'}])}))
    assert report.attrib['tests']=='1' and report.attrib['failures']=='0'
    for data in [result(status='running'),{'operation':'verify','status':'completed'},result(cases=[{'status':'unknown'}])]:
        with pytest.raises(HTTPException):junit(data)


def test_api_scoped_download_selected_import_and_ci_package(tmp_path):
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'CI export'}).json()['id']
        other=client.post('/api/projects',json={'name':'Other'}).json()['id']
        with Session() as db:
            run=add_record(db,pid,'run',result());db.commit();rid=run.id
        assert client.get(f'/api/exports?project_id={other}&format=junit&run_id={rid}').status_code==404
        response=client.get(f'/api/exports?project_id={pid}&format=junit&run_id={rid}')
        assert response.status_code==200 and response.headers['content-type']=='application/xml'
        assert ET.fromstring(response.content).attrib['tests']=='4'
        for name,code in [('test_a.py','def test_a(): assert True'),('test_b.py','def test_b(): assert False')]:
            assert client.post(f'/api/projects/{pid}/files',files={'file':(name,code.encode())}).status_code==201
        assert client.post(f'/api/projects/{pid}/import-tests',json={'paths':['missing.py']}).status_code==422
        assert client.post(f'/api/projects/{pid}/import-tests',json={'paths':['test_a.py','test_a.py']}).status_code==422
        imported=client.post(f'/api/projects/{pid}/import-tests',json={'paths':['test_a.py']})
        assert imported.status_code==201 and imported.json()['imported']==1
        response=client.get(f'/api/exports?project_id={pid}&format=ci');assert response.status_code==200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names=archive.namelist();assert '.github/workflows/debugych-qa.yml' in names
            workflow=archive.read('.github/workflows/debugych-qa.yml').decode()
            assert 'on: workflow_dispatch' in workflow and 'contents: read' in workflow
            assert 'persist-credentials: false' in workflow and 'if: always()' in workflow
            assert 'run: python debugych_ci/run.py' in workflow
            assert all(value not in workflow for value in ('pull_request_target','LLM_API_KEY','OWNER_TOKEN','pip install','npm install'))
            assert not any(name.endswith('test_b.py') for name in names)
            archive.extractall(tmp_path)
        (tmp_path/'calc.py').write_text('def add(a,b): return a+b')
        (tmp_path/'.env').write_text('SECRET=do-not-send')
        (tmp_path/'credentials.json').write_text('secret')
        payload,selected,files=package(tmp_path,tmp_path/'debugych_ci/plan.json')
        assert len(selected)==1 and 'calc.py' in files and '.env' not in files and 'credentials.json' not in files
        assert 'debugych_ci/run.py' not in files and payload
        plan=json.loads((tmp_path/'debugych_ci/plan.json').read_text())
        (tmp_path/plan['tests'][0]['path']).write_text('def test_changed(): pass')
        with pytest.raises(ValueError,match='hash changed'):package(tmp_path,tmp_path/'debugych_ci/plan.json')


@pytest.mark.parametrize('base',['http://example.com','https://name:password@example.com','https://example.com/api','https://example.com?token=x','https://example.com/#x'])
def test_ci_credentials_only_to_exact_https_origin(base):
    with pytest.raises(ValueError):Client(base)


@pytest.mark.parametrize('status,runtime,case_status,expected',[
    ('completed','runsc','passed',0),('completed','runsc','failed',1),
    ('completed','runsc','skipped',1),('failed','runsc','passed',1),('completed','runc','passed',1),
])
def test_downloaded_client_gate_and_cleanup_without_model_calls(tmp_path,monkeypatch,status,runtime,case_status,expected):
    from types import SimpleNamespace
    from uuid import uuid4
    from apps.api import ci_client
    pid=str(uuid4());rid=str(uuid4());tid=str(uuid4());calls=[]
    with zipfile.ZipFile(io.BytesIO(export_ci([SimpleNamespace(id=tid,data={'framework':'pytest','code':'def test_one(): assert True'})]))) as archive:archive.extractall(tmp_path)
    output=tmp_path/'debugych-report'
    summary=dict.fromkeys(('passed','failed','errors','skipped'),0);summary[case_status]=1
    report={'operation':'run','status':status,'runtime':runtime,'cases':[{'name':'one','status':case_status}],**summary}
    class FakeClient:
        def __init__(self,base):pass
        def login(self,username,password):pass
        def json(self,method,path,data=None):
            calls.append((method,path))
            if path=='/api/projects':return {'id':pid}
            if path.endswith('/import-tests'):
                assert data['paths']==[f'debugych_ci/tests/test_{tid}.py'];return {'imported':1}
            if path.endswith('/runs'):return {'id':rid,**report}
            if method=='DELETE':return {'deleted':True}
            raise AssertionError('Unexpected API route')
        def request(self,method,path,*args):
            calls.append((method,path))
            if path.startswith('/api/exports?'):return junit(report)
            assert path.endswith('/files');return b'{}'
    monkeypatch.setattr(ci_client,'Client',FakeClient)
    monkeypatch.setenv('DEBUGYCH_USERNAME','offline-user');monkeypatch.setenv('DEBUGYCH_PASSWORD','offline-password')
    monkeypatch.setattr('sys.argv',['run.py','--root',str(tmp_path),'--output',str(output)])
    assert ci_client.main()==expected
    assert calls[-1]==('DELETE','/api/projects/'+pid)
    assert not any(any(word in path for word in ('analyze','autonomous','fix','ask')) for _,path in calls)
