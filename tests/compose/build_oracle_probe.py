"""Prepare trusted supervisor probe with data literals; never sends oracle to LLM."""
import json
from pathlib import Path
from uuid import uuid4
from stack_smoke import request
ROOT=Path(__file__).resolve().parents[2]
report=json.loads((ROOT/'work/novel-contract-results.json').read_text(encoding='utf-8'))
jobs=[]
for project in report['results']:
    folder=ROOT/'evaluation/projects'/project['name']
    files=[{'path':f.relative_to(folder).as_posix(),'content':f.read_text(encoding='utf-8')} for f in folder.rglob('*') if f.is_file() and f.suffix!='.md']
    fix=next(f for f in request(f"/api/projects/{project['project_id']}/fixes") if f['id']==project['candidates'][0]['fix_id'])
    code=(ROOT/'evaluation/oracle_tests'/('dispatch_checks.py' if project['name']=='python_dispatch' else 'seat_checks.spec.ts')).read_text(encoding='utf-8')
    tests=[{'id':str(uuid4()),'requirement_id':str(uuid4()),'code':code}]
    for stage in ('original','candidate'):
        replacements={c['path']:c['after'] for c in fix['changes']} if stage=='candidate' else {}
        jobs.append({'name':project['name'],'stage':stage,'job':{'id':str(uuid4()),'profile':None if project['name']=='python_dispatch' else 'playwright',
                    'files':[{'path':f['path'],'content':replacements.get(f['path'],f['content'])} for f in files],'tests':tests}})
script='''import json
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot
results=[]
'''
script+='jobs='+repr(jobs)+'\n'
script+='''for item in jobs:
    result=execute_snapshot(SandboxJob.model_validate(item['job']))
    assert result['status']=='completed',result
    if result['failed']!=(2 if item['stage']=='original' else 0):
        print(json.dumps({'unexpected':item['name'],'stage':item['stage'],'cases':result['cases']},ensure_ascii=True),flush=True)
        raise AssertionError('Unexpected oracle result; see case observations')
    results.append({'project':item['name'],'stage':item['stage'],'runtime':result['runtime'],'image_id':result['image_id'],'passed':result['passed'],'failed':result['failed'],'cases':result['cases']})
print(json.dumps({'oracle_never_sent_to_llm':True,'results':results},ensure_ascii=True),flush=True)
'''
(ROOT/'work/oracle-probe.py').write_text(script,encoding='utf-8')
print('Prepared data-only oracle probe for 4 isolated executions')
