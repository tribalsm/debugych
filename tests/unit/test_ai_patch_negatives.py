from uuid import uuid4
import pytest
from apps.api.bug_workflow import prepare_patch,digest

def snapshot(path='SeatDesk.tsx',content='export const available = 6;'):
    return {'id':str(uuid4()),'profile':'playwright','files':[{'path':'index.html','content':'<div>App</div>'},{'path':path,'content':content}],
            'tests':[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':"import {test} from '@playwright/test';"}]}

@pytest.mark.parametrize('path',['tests/SeatDesk.tsx','SeatDesk.spec.ts','playwright.config.ts','package.json','index.html'])
def test_browser_patch_cannot_change_tests_config_or_html(path):
    original='export const available = 6;' if path.endswith(('.ts','.tsx')) else '{}'
    snap=snapshot(path,original)
    plan={'explanation':'Bad candidate','changes':[{'path':path,'before_sha256':digest(original),'content':original+'\n// changed'}]}
    with pytest.raises(ValueError):prepare_patch(snap,plan)

def test_secret_source_cannot_be_overwritten_with_redaction():
    original='API_KEY="customer-sensitive-token"\nvalue=1'
    snap={'id':str(uuid4()),'files':[{'path':'app.py','content':original}],
          'tests':[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':'def test_one(): assert True'}]}
    with pytest.raises(ValueError,match='секрет'):
        prepare_patch(snap,{'explanation':'Unsafe redaction','changes':[{'path':'app.py','before_sha256':digest(original),'content':'value=2'}]})
