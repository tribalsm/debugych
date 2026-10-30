"""Import data-only user tests. Uploaded code is never imported by the backend."""
import ast
import re
from pathlib import PurePosixPath
from sqlalchemy import select
from fastapi import HTTPException
from apps.api.db import Record,add_record,serialize
from apps.api.jobs import DATA

def import_tests(db,pid,selection=None):
    from apps.api.bug_workflow import lock_project
    project=lock_project(db,pid)
    if project.demo:raise HTTPException(409,'Для демо используйте подготовленный тестовый план.')
    if db.scalar(select(Record).where(Record.project_id==pid,Record.kind=='test')):
        raise HTTPException(409,'Набор тестов уже существует. Он не будет автоматически заменён.')
    files=db.scalars(select(Record).where(Record.project_id==pid,Record.kind=='file')).all()
    if selection is not None and selection != {}:
        paths=selection.get('paths')
        if set(selection)!={'paths'} or not isinstance(paths,list) or not 1<=len(paths)<=40 or any(not isinstance(p,str) for p in paths) or len(set(paths))!=len(paths):
            raise HTTPException(422,'Передайте от 1 до 40 уникальных путей тестов')
        if not set(paths)<= {row.data['name'] for row in files}:
            raise HTTPException(422,'Выбранный файл не найден в проекте')
        files=[row for row in files if row.data['name'] in paths]
    candidates=[]
    for row in files:
        name=row.data['name'];base=PurePosixPath(name).name
        framework='pytest' if base.endswith('.py') and (base.startswith('test_') or base.endswith('_test.py')) else 'playwright' if re.search(r'\.(spec|test)\.(js|mjs|cjs|ts|tsx|jsx)$',base) else None
        if not framework:
            if selection and selection.get('paths'):raise HTTPException(422,'Выбранный файл не является тестовым модулем')
            continue
        try:code=(DATA/row.data['storage']).read_text(encoding='utf-8-sig')
        except UnicodeError:raise HTTPException(422,f'{name}: сохраните кодировку UTF-8.') from None
        if not code.strip() or len(code)>16000:raise HTTPException(422,f'{name}: тестовый модуль должен содержать до 16000 символов.')
        if framework=='pytest':
            try:tree=ast.parse(code)
            except SyntaxError as error:raise HTTPException(422,f'{name}: синтаксическая ошибка Python, строка {error.lineno}.') from None
            if any(isinstance(n,ast.ImportFrom) and n.level for n in ast.walk(tree)):
                raise HTTPException(422,f'{name}: используйте абсолютные импорты модулей проекта.')
            if not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(tree)):
                raise HTTPException(422,f'{name}: не найдены функции test_*.')
        candidates.append((name,framework,code))
    if not candidates:raise HTTPException(422,'Добавьте test_*.py / *_test.py или *.spec.ts / *.test.js с собственными тестами. Для генерации тестов из требований войдите в аккаунт.')
    if len(candidates)>40 or len({f for _,f,_ in candidates})!=1:raise HTTPException(422,'До 40 модулей одного типа: pytest или Playwright.')
    marker=add_record(db,pid,'requirement',{'key':'USER_TESTS','text':'Ожидания из пользовательских тестов. Соответствие документу требований не проверено.','source':'uploaded-tests','user_assertions':True})
    saved=[]
    for name,framework,code in candidates:
        row=add_record(db,pid,'test',{'title':name,'framework':framework,'code':code,'gherkin':'','requirement':'USER_TESTS','requirement_id':marker.id,'origin':'uploaded-user-tests','source_test_path':name,'result':'not_run','notice':'Пользовательский тест. Ожидания не проверены LLM.'})
        saved.append(serialize(row))
    db.commit();return {'imported':len(saved),'tests':saved,'notice':'Тесты импортированы без обращения к LLM. Исполнение происходит только в gVisor.'}

def delete_project(db,pid):
    from apps.api.bug_workflow import lock_project
    from apps.api.run_artifacts import directory
    project=lock_project(db,pid)
    rows=db.scalars(select(Record).where(Record.project_id==pid)).all()
    if any(r.kind in ('run','companion_chat') and r.data.get('status') in ('queued','running','analyzing','generating') for r in rows):
        raise HTTPException(409,'Сначала дождитесь завершения заданий проекта.')
    targets=[]
    def add(base,identity):
        from uuid import UUID
        try:identity=str(UUID(identity))
        except (ValueError,TypeError,AttributeError):return
        base=base.resolve();target=(base/identity).resolve()
        if target.parent!=base:raise HTTPException(409,'Небезопасный путь данных')
        targets.append(target)
    def artifacts(value):
        if not isinstance(value,dict):return
        for item in value.get('artifacts',[]):
            if isinstance(item,dict):add(directory(),item.get('id'))
        for key in ('baseline','focused','regression','replay'):artifacts(value.get(key))
    for row in rows:
        if row.kind=='file':add(DATA,row.data.get('storage'))
        if row.kind=='run':artifacts(row.data)
        if row.kind=='fix':
            for item in row.data.get('application',{}).get('files',[]):
                add(DATA,item.get('before_storage'));add(DATA,item.get('after_storage'))
    for target in set(targets):target.unlink(missing_ok=True)
    for row in rows:db.delete(row)
    from apps.api.db import ContextChunk
    from sqlalchemy import delete
    db.execute(delete(ContextChunk).where(ContextChunk.project_id==pid))
    db.delete(project);db.commit();return {'deleted':True,'project_id':pid}
