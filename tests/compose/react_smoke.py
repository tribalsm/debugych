import json
from uuid import uuid4
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot
job=SandboxJob(id=uuid4(),profile='playwright',files=[
 {'path':'index.html','content':'<div id="root"></div><script type="module" src="/main.tsx"></script>'},
 {'path':'style.css','content':'h1 { color: rgb(0, 128, 0); }'},
 {'path':'main.tsx','content':'''import React from 'react'; import {createRoot} from 'react-dom/client'; import './style.css';
createRoot(document.getElementById('root')!).render(<h1>React TSX works</h1>);'''}],
 tests=[{'id':uuid4(),'requirement_id':uuid4(),'code':"""import {test,expect} from '@playwright/test';
test('React, TSX and bundled CSS',async({page})=>{await page.goto('/');await expect(page.getByRole('heading')).toHaveText('React TSX works');await expect(page.getByRole('heading')).toHaveCSS('color','rgb(0, 128, 0)');});"""}])
result=execute_snapshot(job)
print(json.dumps({**result,'artifacts':[{k:v for k,v in a.items() if k!='data'} for a in result.get('artifacts',[])]},ensure_ascii=True),flush=True)
assert result['status']=='completed' and result['passed']==1 and not result['errors'],result
assert result['coverage'] and any(a['name']=='screenshot-1.png' for a in result['artifacts'])
