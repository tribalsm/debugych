"""Create immutable source/test snapshots without importing uploaded Python."""
import ast
from uuid import uuid4
from sqlalchemy import select
from apps.api.db import Record
from apps.api.jobs import DATA
from services.runner.contracts import SandboxJob

def snapshot_project(db, project_id):
    files = db.scalars(select(Record).where(Record.project_id==project_id,Record.kind=='file')).all()
    tests = db.scalars(select(Record).where(Record.project_id==project_id,Record.kind=='test')).all()
    frameworks={t.data['framework'] for t in tests}
    if not tests or frameworks not in ({'pytest'},{'playwright'}):
        raise ValueError('Нужен однородный план pytest или Playwright; смешанные планы не поддерживаются.')
    browser=frameworks=={'playwright'}
    suffixes=('.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css','.json') if browser else ('.py',)
    imported={t.data.get('source_test_path') for t in tests if t.data.get('origin')=='uploaded-user-tests'}
    source = [{'path':f.data['name'],'content':(DATA / f.data['storage']).read_bytes().decode('utf-8-sig')} for f in files if f.data['name'].lower().endswith(suffixes) and f.data['name'] not in imported]
    generated = []
    for test in tests:
        if not browser:
            ast.parse(test.data['code'])
        generated.append({'id':test.id,'requirement_id':test.data['requirement_id'],'code':test.data['code']})
    return SandboxJob(id=uuid4(),profile='playwright' if browser else None,files=source,tests=generated).model_dump(mode='json',exclude_none=True)
