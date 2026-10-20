import base64
import json
import struct
import zlib
from uuid import uuid4
import pytest
from pydantic import ValidationError
from services.runner.contracts import SandboxJob, Artifact
from apps.api.uploads import validate
from services.ai.engine import FailureAnalyzer

def png():
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b'')

def job(**change):
    return {'id':str(uuid4()),'profile':'playwright','files':[{'path':'index.html','content':'<h1>Hi</h1>'},{'path':'main.ts','content':'let n: number = 1;'}],
            'tests':[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':"import {test} from '@playwright/test';"}],**change}

def test_profile_language_binding_and_required_index():
    browser=SandboxJob.model_validate(job())
    assert browser.profile=='playwright'
    for overrides in ({'profile':None},{'profile':'node-shell'},{'files':[{'path':'x.py','content':'pass'}]},
                      {'files':[{'path':'main.ts','content':'let n=0;'}]}, {'command':'npm install'}):
        with pytest.raises(ValidationError):SandboxJob.model_validate(job(**overrides))

@pytest.mark.parametrize('extension',['js','mjs','cjs','ts','tsx','jsx','html','css','json'])
def test_source_uploads_are_utf8_data(extension):
    assert validate('app.'+extension,b'content')=='.'+extension
    with pytest.raises(ValueError):validate('app.'+extension,b'\x00bad')

def test_artifact_validation_prevents_active_content_and_oversize():
    image={'name':'screenshot-1.png','media_type':'image/png','data':base64.b64encode(png()).decode()}
    assert Artifact.model_validate(image).name=='screenshot-1.png'
    for change in ({'name':'../x.png'},{'name':'index.html'},{'media_type':'text/html'},
                   {'data':base64.b64encode(b'<script>alert(1)</script>').decode()},
                   {'data':base64.b64encode(png()[:-2]).decode()},{'data':'not base64'},
                   {'data':base64.b64encode(b'x'*400001).decode()}):
        with pytest.raises((ValueError,ValidationError)):Artifact.model_validate({**image,**change})
    assert Artifact(name='report.json',media_type='application/json',data=base64.b64encode(json.dumps({'ok':True}).encode()).decode())

def test_playwright_assertion_and_timeout_are_distinguished():
    assert FailureAnalyzer.classify({'status':'failed','traceback':'Error: expect(locator).toHaveText(expected) failed'},True)=='reproduced'
    assert FailureAnalyzer.classify({'status':'error','traceback':'Test timeout exceeded'})=='infrastructure'
