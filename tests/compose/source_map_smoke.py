"""Real gVisor: original TS line/branch coverage, never generated helper lines."""
import json
from uuid import uuid4
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot

rules="type Amount = number;\nexport function describe(n: Amount): string {\n  if (n === 0) {\n    return 'Empty';\n  }\n  return 'Active';\n}\n"
job=SandboxJob(id=uuid4(),profile='playwright',files=[
    {'path':'index.html','content':'<button>Check</button><output></output><script type="module" src="/main.ts"></script>'},
    {'path':'rules.ts','content':rules},
    {'path':'main.ts','content':"import {describe} from './rules';\ndocument.querySelector('button')!.onclick=()=>{document.querySelector('output')!.textContent=describe(0)};"}],
    tests=[{'id':uuid4(),'requirement_id':uuid4(),'code':"import {test,expect} from '@playwright/test';test('original TypeScript lines',async({page})=>{await page.goto('/');await page.getByRole('button').click();await expect(page.locator('output')).toHaveText('Empty')});"}])
result=execute_snapshot(job)
assert result['status']=='completed' and result['passed']==1 and result['runtime']=='runsc',result.get('error')
assert result['coverage_kind']=='istanbul-original-source'
coverage=result['coverage'];file=coverage['files']['rules.ts']
assert 4 in file['executed_lines'] and 6 in file['missing_lines'] and 1 not in file['executed_lines'],file
assert coverage['totals']['covered_branches']<coverage['totals']['num_branches']
assert all(not name.endswith('.compiled.js') for name in coverage['files'])
print(json.dumps({'runtime':result['runtime'],'passed':result['passed'],'coverage_kind':result['coverage_kind'],'coverage':coverage}))
