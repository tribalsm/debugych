import os
import httpx
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from apps.api.db import Base, engine, Session, Project, Record, serialize, add_record
from apps.api.uploads import unpack, MAX_FILE
from apps.api.jobs import dispatch, DATA, ROOT
from services.ai.engine import FixGenerator

@asynccontextmanager
async def lifespan(app):
    # Local mode only; Compose applies Alembic before accepting connections.
    if os.getenv('TASK_MODE', 'local') == 'local':
        from alembic.config import Config
        from alembic import command
        config = Config(str(ROOT / 'alembic.ini'))
        config.set_main_option('script_location', str(ROOT / 'infra/migrations'))
        command.upgrade(config, 'head')
    DATA.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title='Дебагыч · AI QA Assistant', lifespan=lifespan)
from apps.api.access import OwnerAccess
app.add_middleware(OwnerAccess)
from apps.api.companion_chat import router as companion_chat_router
app.include_router(companion_chat_router)

from services.ai.adapter import AIError
@app.exception_handler(AIError)
async def ai_error_handler(request,error):
    return JSONResponse(status_code=503,content={'detail':str(error),'code':error.code})

@app.get('/api/demo-web', response_class=Response)
def demo_web():
    return Response((ROOT / 'demo/sample-web-app/index.html').read_text(encoding='utf-8'), media_type='text/html')

class NewProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)

class EditTest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    gherkin: str = Field(min_length=1, max_length=8000)
    code: str = Field(min_length=1, max_length=16000)

class Approval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: bool
    fix_id: UUID | None = None
    verification_id: UUID | None = None
    patch_sha256: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')

class ProofReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm_expectation: bool
    reviewer_note: str = Field(min_length=12,max_length=2000)
    run_id: UUID
    test_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

class FixChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    fix_id: UUID | None = None

class DraftAcceptance(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: bool
    analysis_id: UUID
    draft_index: int = Field(ge=0,le=1)
    draft_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    project_state_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewer_note: str = Field(min_length=12,max_length=2000)
    reviewer_kind: Literal['human','agent']

class AIConsent(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: bool
    project_state_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    provider_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')

class AIRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    consent: AIConsent

def project_or_404(db, pid):
    project = db.get(Project, str(pid))
    if not project:
        raise HTTPException(404, 'Проект не найден')
    return project

def record_or_404(db, rid, kind=None):
    row = db.get(Record, str(rid))
    if not row or (kind and row.kind != kind):
        raise HTTPException(404, 'Запись не найдена')
    return row

@app.get('/api/health')
def health():
    with engine.connect() as connection:
        from sqlalchemy import text
        connection.execute(text('SELECT 1'))
    sandbox = sandbox_health()
    from apps.api.ai_runtime import status
    ai=status()
    return {'status': 'ok', 'ai_available': ai['configured'], 'ai_status':ai['status'],'ai_provider_mode':os.getenv('LLM_PROVIDER_MODE','live'), 'execution': 'gvisor-python' if sandbox else 'trusted-demo-only',
            'sandbox_configured':os.getenv('SANDBOX_ENABLED')=='1','sandbox_available':bool(sandbox),
            'playwright_available':bool(sandbox and sandbox.get('playwright_image_id'))}

@app.get('/api/ai/status')
def ai_status():
    from apps.api.ai_runtime import status
    return status()

@app.get('/api/projects/{pid}/ai-context')
def ai_context(pid: UUID):
    from apps.api.ai_runtime import preview
    with Session() as db:
        from apps.api.bug_workflow import lock_project
        lock_project(db,str(pid))
        return preview(db,str(pid))

@app.get('/api/projects/{pid}/ai-statistics')
def ai_statistics(pid: UUID):
    with Session() as db:
        project_or_404(db,pid)
        calls=[serialize(r) for r in db.scalars(select(Record).where(Record.project_id==str(pid),Record.kind=='ai_call').order_by(Record.created_at))]
        return {'attempts':len(calls),'succeeded':sum(c['outcome']=='succeeded' for c in calls),'failed':sum(c['outcome']!='succeeded' for c in calls),
                'reserved_tokens':sum(c['reserved_tokens'] for c in calls),'reserved_cost_micro_usd':sum(c['reserved_cost_micro_usd'] for c in calls),
                'provider_usage_available':sum(c['usage'] is not None for c in calls),'calls':calls,
                'notice':'Успех JSON-генерации не означает корректность тестов. Резервы — верхняя оценка по настроенным тарифам, не счёт провайдера.'}

def sandbox_health():
    if os.getenv('SANDBOX_ENABLED')!='1':
        return None
    try:
        response = httpx.get(os.getenv('SUPERVISOR_URL','http://127.0.0.1:8091')+'/health',timeout=2,trust_env=False)
        response.raise_for_status()
        value = response.json()
        return value if value.get('runtime')=='runsc' and value.get('status')=='ok' else None
    except Exception:
        return None

@app.get('/api/projects')
def projects():
    with Session() as db:
        return [serialize(p) for p in db.scalars(select(Project).order_by(Project.created_at.desc()))]

@app.get('/api/storage-usage')
def storage_usage():
    from sqlalchemy import func,cast,Text
    from apps.api.run_artifacts import directory
    total=0
    for folder in (DATA,directory()):
        if folder.is_dir():
            total+=sum(p.stat().st_size for p in folder.iterdir() if p.is_file() and not p.is_symlink())
    with Session() as db:
        # Four bytes per character conservatively bound UTF-8 JSON payloads.
        total+=4*(db.scalar(select(func.sum(func.length(cast(Record.data,Text))))) or 0)
    return {'estimated_bytes':total}

@app.post('/api/projects', status_code=201)
def create_project(value: NewProject):
    if not value.name.strip():
        raise HTTPException(422, 'Название не может состоять из пробелов')
    with Session() as db:
        project = Project(name=value.name.strip())
        db.add(project)
        db.commit()
        return serialize(project)

@app.post('/api/demo', status_code=201)
def create_demo():
    with Session() as db:
        project = Project(name='Shop API · граничные значения', demo=True)
        db.add(project)
        db.flush()
        for name in ['shop.py', 'requirements.md']:
            storage = str(uuid4())
            content = (ROOT / 'demo/sample-python-app' / name).read_bytes()
            DATA.mkdir(parents=True, exist_ok=True)
            (DATA / storage).write_bytes(content)
            add_record(db, project.id, 'file', {'name': name, 'size': len(content), 'storage': storage})
        db.commit()
        return serialize(project)

@app.get('/api/projects/{pid}')
def project(pid: UUID):
    with Session() as db:
        return serialize(project_or_404(db, pid))

@app.post('/api/projects/{pid}/files', status_code=201)
async def upload(pid: UUID, file: UploadFile = File(...)):
    content = await file.read(MAX_FILE + 1)
    if len(content) > MAX_FILE:
        raise HTTPException(413, 'Максимальный размер загрузки 10 МБ')
    try:
        entries = unpack(file.filename or '', content)
    except Exception as error:
        raise HTTPException(422, f'Файл отклонён: {error}') from error
    with Session() as db:
        project = project_or_404(db, pid)
        from apps.api.bug_workflow import lock_project
        lock_project(db,str(pid))
        if project.demo:
            raise HTTPException(409, 'Демо использует неизменяемую доверенную fixture. Создайте обычный проект для своих файлов.')
        saved = []
        try:
            for name, payload in entries:
                storage = str(uuid4())
                (DATA / storage).write_bytes(payload)
                saved.append(storage)
                add_record(db, str(pid), 'file', {'name': name, 'size': len(payload), 'storage': storage})
            db.commit()
        except Exception:
            db.rollback()
            for storage in saved:
                (DATA / storage).unlink(missing_ok=True)
            raise
    return {'uploaded': len(entries)}

def new_job(db, pid, operation, background, _prepare=None, **data):
    from apps.api.bug_workflow import lock_project
    lock_project(db,str(pid))
    active = db.scalars(select(Record).where(Record.project_id == str(pid), Record.kind == 'run')).all()
    if any(r.data.get('status') in ['queued', 'analyzing', 'generating', 'running'] for r in active):
        raise HTTPException(409, 'Дождитесь завершения текущего задания')
    job = add_record(db, str(pid), 'run', {'status': 'queued', 'operation': operation, **data})
    if 'snapshot' in data:
        from services.runner.contracts import SandboxJob
        snapshot = SandboxJob.model_validate({**data['snapshot'],'id':job.id})
        job.data = {**job.data,'snapshot':snapshot.model_dump(mode='json'),'snapshot_sha256':snapshot.fingerprint()}
        rows=db.scalars(select(Record).where(Record.project_id==str(pid),Record.kind.in_(['test','requirement']))).all()
        job.data={**job.data,'quality_inputs':{
            'requirement_ids':[r.id for r in rows if r.kind=='requirement'],
            'tests':[{'id':r.id,'requirement_id':r.data['requirement_id'],'dimensions':r.data.get('dimensions',[])} for r in rows if r.kind=='test']}}
    if _prepare:
        _prepare(job)
    db.commit()
    result = serialize(job)
    try:
        dispatch(job.id, background)
    except Exception as error:
        job.data = {**job.data, 'status': 'failed', 'error': 'Очередь заданий недоступна'}
        db.commit()
        raise HTTPException(503, 'Очередь заданий недоступна') from error
    return result

@app.post('/api/projects/{pid}/analyze', status_code=202)
def analyze(pid: UUID, background: BackgroundTasks,value: AIRequest | None = None):
    with Session() as db:
        from apps.api.bug_workflow import lock_project,state_hash
        project = lock_project(db,str(pid))
        if not project.demo and not os.getenv('LLM_API_KEY'):
            raise HTTPException(503, 'AI недоступен: задайте LLM_API_KEY или откройте Демо')
        if not project.demo and db.scalar(select(Record).where(Record.project_id==str(pid),Record.kind=='test')):
            raise HTTPException(409,'План уже существует; редактируйте его в Test Studio или создайте новый проект')
        grant=None
        if not project.demo:
            from apps.api.ai_runtime import consent
            grant=consent(db,str(pid),value.consent if value else None)
        return new_job(db, pid, 'analyze', background,ai_consent=grant)

@app.post('/api/projects/{pid}/autonomous',status_code=202)
def autonomous(pid: UUID,background: BackgroundTasks,value: AIRequest):
    from apps.api.ai_runtime import consent
    from apps.api.bug_workflow import lock_project
    with Session() as db:
        project=lock_project(db,str(pid))
        if project.demo:raise HTTPException(409,'Автономный workflow предназначен для загруженных проектов')
        if not os.getenv('LLM_API_KEY'):raise HTTPException(503,'Настройте LLM_API_KEY')
        if os.getenv('SANDBOX_ENABLED')!='1' or not sandbox_health():raise HTTPException(503,'Требуется gVisor')
        if db.scalar(select(Record).where(Record.project_id==str(pid),Record.kind.in_(['test','requirement']))):
            raise HTTPException(409,'Нужен новый проект без ранее созданного плана')
        grant=consent(db,str(pid),value.consent)
        return new_job(db,pid,'autonomous',background,ai_consent={**grant,'scope':'autonomous_qa'})

@app.post('/api/projects/{pid}/accept-ai-draft',status_code=201)
def accept_ai_draft(pid: UUID,value: DraftAcceptance):
    """Explicit review of a stored, never-executed draft. No LLM call or patch."""
    import json
    from apps.api.bug_workflow import lock_project,state_hash,digest
    from services.ai.engine import Plan,TestPlanner
    from services.ai.privacy import redact
    if not value.confirm:raise HTTPException(409,'Требуется явное подтверждение проверки черновика')
    with Session() as db:
        project=lock_project(db,str(pid))
        analysis=db.get(Record,str(value.analysis_id))
        if not analysis or analysis.project_id!=str(pid) or analysis.kind!='run':
            raise HTTPException(404,'Анализ проекта не найден')
        if analysis.data.get('operation')!='analyze' or analysis.data.get('status')!='failed':
            raise HTTPException(409,'Принимать можно только черновик завершённого неуспешного анализа')
        current=state_hash(db,str(pid))
        if current!=value.project_state_sha256 or current!=analysis.data.get('ai_consent',{}).get('project_state_sha256'):
            raise HTTPException(409,'Проект изменился после генерации')
        rows=db.scalars(select(Record).where(Record.project_id==str(pid))).all()
        if any(r.kind in ('requirement','test') or (r.kind=='run' and r.data.get('status') in ('queued','analyzing','generating','running')) for r in rows):
            raise HTTPException(409,'У проекта уже есть план или активное задание')
        drafts=analysis.data.get('generation_review',{}).get('drafts',[])
        if value.draft_index>=len(drafts):raise HTTPException(404,'Черновик не найден')
        stored=drafts[value.draft_index]['plan']
        if digest(json.dumps(stored,sort_keys=True,ensure_ascii=False))!=value.draft_sha256:
            raise HTTPException(409,'SHA черновика не совпадает')
        try:plan=TestPlanner.validate(Plan.model_validate(stored),require_all=True)
        except ValueError:raise HTTPException(422,'Черновик не прошёл структурную проверку') from None
        framework='pytest' if any(r.kind=='file' and r.data['name'].endswith('.py') for r in rows) else 'playwright'
        if any(s.framework!=framework for s in plan.scenarios):raise HTTPException(422,'Профиль черновика не соответствует проекту')
        review={'analysis_id':analysis.id,'draft_index':value.draft_index,'draft_sha256':value.draft_sha256,
                'project_state_sha256':current,'reviewer_kind':value.reviewer_kind,'reviewer_note':redact(value.reviewer_note)[0]}
        reqs={r.key:add_record(db,str(pid),'requirement',r.model_dump()).id for r in plan.requirements}
        for scenario in plan.scenarios:
            add_record(db,str(pid),'test',{**scenario.model_dump(),'requirement_id':reqs[scenario.requirement],
                'origin':'llm-reviewed-draft','draft_review':review,'result':'not_run'})
        row=add_record(db,str(pid),'run',{'operation':'accept_draft','status':'completed','draft_review':review,
            'notice':'Explicit review; the LLM reviewer rejected this draft. Original failed analysis retained.'})
        db.commit()
        return serialize(row)

@app.post('/api/projects/{pid}/runs', status_code=202)
def run(pid: UUID, background: BackgroundTasks):
    with Session() as db:
        from apps.api.bug_workflow import lock_project,state_hash
        project = lock_project(db,str(pid))
        if not project.demo:
            if os.getenv('SANDBOX_ENABLED')!='1':
                raise HTTPException(403, 'Изолированный runner не настроен. Запустите Compose с gVisor.')
            if not sandbox_health():
                raise HTTPException(503,'gVisor Runner недоступен. Исполнение закрыто без небезопасного fallback.')
            from apps.api.snapshots import snapshot_project
            try:
                snapshot = snapshot_project(db,str(pid))
            except (ValueError,SyntaxError) as error:
                raise HTTPException(422,str(error)) from error
            if snapshot.get('profile')=='playwright' and not (sandbox_health() or {}).get('playwright_image_id'):
                raise HTTPException(503,'Playwright gVisor image недоступен')
            return new_job(db,pid,'run',background,snapshot=snapshot,project_state_sha256=state_hash(db,str(pid)))
        if not db.scalar(select(Record).where(Record.project_id == str(pid), Record.kind == 'test')):
            raise HTTPException(409, 'Сначала создайте тестовый план')
        applied = any(r.data.get('applied') for r in db.scalars(select(Record).where(Record.project_id == str(pid), Record.kind == 'fix')))
        return new_job(db, pid, 'run', background, fixed=applied)

@app.post('/api/projects/{pid}/import-tests',status_code=201)
def import_uploaded_tests(pid: UUID, selection: dict | None = None):
    from apps.api.user_tests import import_tests
    with Session() as db:return import_tests(db,str(pid), selection)

@app.delete('/api/projects/{pid}')
def delete_uploaded_project(pid: UUID):
    from apps.api.user_tests import delete_project
    with Session() as db:return delete_project(db,str(pid))

@app.get('/api/test-cases/{tid}')
def test_case(tid: UUID):
    with Session() as db:return serialize(record_or_404(db,tid,'test'))

@app.patch('/api/test-cases/{tid}')
def edit_test(tid: UUID, value: EditTest):
    with Session() as db:
        row = record_or_404(db, tid, 'test')
        from apps.api.bug_workflow import lock_project
        lock_project(db,row.project_id)
        db.refresh(row)
        if project_or_404(db, row.project_id).demo:
            raise HTTPException(409, 'Доверенные демотесты неизменяемы. В обычном проекте сценарии можно редактировать.')
        row.data = {**row.data, **value.model_dump(), 'result': 'not_run'}
        db.commit()
        return serialize(row)

@app.get('/api/runs/{rid}')
def get_run(rid: UUID):
    with Session() as db:
        return {k:v for k,v in serialize(record_or_404(db, rid, 'run')).items() if k!='snapshot'}

@app.get('/api/runs/{rid}/coverage')
def coverage(rid: UUID):
    with Session() as db:
        row = record_or_404(db, rid, 'run')
        if 'coverage' not in row.data:
            raise HTTPException(404, 'Измеренного покрытия пока нет')
        return row.data['coverage']

@app.get('/api/runs/{rid}/artifacts')
def artifacts(rid: UUID):
    with Session() as db:
        row = record_or_404(db, rid, 'run')
        return {'logs': row.data.get('logs', ''), 'cases': row.data.get('cases', []),'artifacts':row.data.get('artifacts',[])}

@app.get('/api/runs/{rid}/artifacts/{aid}')
def download_artifact(rid: UUID,aid: UUID):
    from apps.api.run_artifacts import find,directory
    with Session() as db:
        row=record_or_404(db,rid,'run')
        artifact=find(row.data,str(aid))
        if not artifact:
            raise HTTPException(404,'Артефакт не принадлежит этому запуску')
        path=directory() / str(aid)
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404,'Артефакт недоступен')
        raw=path.read_bytes()
        import hashlib
        if len(raw)!=artifact['size'] or hashlib.sha256(raw).hexdigest()!=artifact['sha256']:
            raise HTTPException(409,'Артефакт изменился после сохранения')
        return Response(raw,media_type=artifact['media_type'],headers={
            'Content-Disposition':f'attachment; filename="{artifact["name"]}"',
            'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox",'Cache-Control':'private, no-store'})

@app.get('/api/bugs')
def bugs(project_id: UUID | None = None):
    with Session() as db:
        query = select(Record).where(Record.kind == 'bug')
        if project_id:
            query = query.where(Record.project_id == str(project_id))
        return [serialize(r) for r in db.scalars(query.order_by(Record.created_at.desc(),Record.id))]

@app.get('/api/bugs/{bid}')
def bug(bid: UUID):
    with Session() as db:
        return serialize(record_or_404(db, bid, 'bug'))

@app.post('/api/bugs/{bid}/confirm-proof',status_code=202)
def confirm_proof(bid: UUID,review: ProofReview,background: BackgroundTasks):
    from apps.api.bug_workflow import lock_project,current,case_map,target_key
    from services.ai.engine import FailureAnalyzer
    with Session() as db:
        bug=record_or_404(db,bid,'bug')
        project=lock_project(db,bug.project_id); db.refresh(bug)
        if project.demo or bug.data['status'] not in ('reproduced','suspected'):
            raise HTTPException(409,'Подтверждение доступно для воспроизведённой проблемы загрузки')
        if not review.confirm_expectation or len(review.reviewer_note.strip())<12:
            raise HTTPException(409,'Подтвердите соответствие assertion требованию и объясните ожидание')
        original=current(db,bug)
        if str(review.run_id)!=original.id or review.test_sha256!=bug.data.get('test_sha256'):
            raise HTTPException(409,'Рассмотренный тест или запуск изменились')
        try:
            cases=case_map(original.data)
            if FailureAnalyzer.classify(cases[target_key(bug)],True,False)!='reproduced':
                raise ValueError('Нет проверяемого assertion-падения')
        except (ValueError,KeyError) as error:
            raise HTTPException(409,str(error)) from error
        if not sandbox_health():
            raise HTTPException(503,'gVisor Runner недоступен')
        return new_job(db,bug.project_id,'confirm_proof',background,bug_id=bug.id,review=review.model_dump(mode='json'))

@app.post('/api/bugs/{bid}/propose-fix')
def propose(bid: UUID,background: BackgroundTasks,value: AIRequest | None = None):
    with Session() as db:
        bug = record_or_404(db, bid, 'bug')
        from apps.api.bug_workflow import lock_project,current
        project=lock_project(db,bug.project_id); db.refresh(bug)
        if bug.data['status'] not in ['confirmed', 'fix_verified']:
            raise HTTPException(409, 'Требуется подтверждённая проблема')
        if not project.demo:
            original=current(db,bug)
            if not bug.data.get('proof_id'):
                raise HTTPException(409,'Нет проверенного Bug Proof')
            if not os.getenv('LLM_API_KEY'):
                raise HTTPException(503,'AI недоступен: настройте LLM_API_KEY для генерации патча')
            from apps.api.ai_runtime import consent
            grant=consent(db,bug.project_id,value.consent if value else None)
            return JSONResponse(status_code=202,content=new_job(db,bug.project_id,'propose_fix',background,bug_id=bug.id,proof_id=bug.data['proof_id'],ai_consent=grant))
        existing = next((r for r in db.scalars(select(Record).where(Record.project_id == bug.project_id, Record.kind == 'fix')) if r.data['bug_id'] == bug.id), None)
        if existing:
            return serialize(existing)
        source = (ROOT / 'demo/sample-python-app/shop.py').read_text(encoding='utf-8')
        fix = add_record(db, bug.project_id, 'fix', {**FixGenerator.demo_patch(source), 'bug_id': bug.id, 'verified': False, 'applied': False})
        db.commit()
        return serialize(fix)

@app.post('/api/bugs/{bid}/verify-fix', status_code=202)
def verify(bid: UUID, background: BackgroundTasks,choice: FixChoice | None = None):
    with Session() as db:
        bug = record_or_404(db, bid, 'bug')
        from apps.api.bug_workflow import lock_project,current
        project=lock_project(db,bug.project_id); db.refresh(bug)
        if not project.demo:
            original=current(db,bug)
            fix=record_or_404(db,(choice.fix_id if choice else None) or bug.data.get('current_fix_id') or '', 'fix')
            if fix.project_id!=bug.project_id or fix.data['bug_id']!=bug.id or fix.data.get('applied'):
                raise HTTPException(409,'Предложение не относится к этой проблеме или уже применено')
            if bug.data['status'] not in ('confirmed','fix_verified') or fix.data.get('proof_id')!=bug.data.get('proof_id'):
                raise HTTPException(409,'Требуется актуальное подтверждённое доказательство')
            if not sandbox_health():
                raise HTTPException(503,'gVisor Runner недоступен')
            def invalidate(job):
                fix.data={**fix.data,'verified':False,'verification_id':job.id,'assessment':None,
                          'verification_ids':[*fix.data.get('verification_ids',[]),job.id]}
                if bug.data.get('current_fix_id')==fix.id:
                    bug.data={**bug.data,'status':'confirmed'}
            return new_job(db,bug.project_id,'verify',background,_prepare=invalidate,bug_id=bug.id,fix_id=fix.id,patch_sha256=fix.data['patch_sha256'])
        fixes = db.scalars(select(Record).where(Record.project_id == bug.project_id, Record.kind == 'fix')).all()
        fix = next((r for r in fixes if r.data['bug_id'] == bug.id), None)
        if not fix:
            raise HTTPException(409, 'Сначала получите патч')
        return new_job(db, bug.project_id, 'verify', background, bug_id=bug.id, fix_id=fix.id)

@app.post('/api/bugs/{bid}/apply-fix')
def apply_fix(bid: UUID, approval: Approval):
    if not approval.confirm:
        raise HTTPException(409, 'Необходимо явное подтверждение применения')
    with Session() as db:
        bug = record_or_404(db, bid, 'bug')
        if not project_or_404(db,bug.project_id).demo:
            from apps.api.bug_workflow import apply_uploaded
            fix=record_or_404(db,approval.fix_id or '', 'fix')
            if fix.project_id!=bug.project_id or fix.data['bug_id']!=bug.id:
                raise HTTPException(409,'Предложение не относится к этой проблеме')
            return serialize(apply_uploaded(db,bug,fix,approval))
        fix = next((r for r in db.scalars(select(Record).where(Record.project_id == bug.project_id, Record.kind == 'fix')) if r.data['bug_id'] == bug.id), None)
        if not fix or not fix.data.get('verified'):
            raise HTTPException(409, 'Сначала успешно проверьте патч')
        file = next(r for r in db.scalars(select(Record).where(Record.project_id == bug.project_id, Record.kind == 'file')) if r.data['name'] == 'shop.py')
        path = DATA / file.data['storage']
        if fix.data.get('applied'):
            return serialize(fix)
        if path.read_text(encoding='utf-8') != fix.data['before']:
            raise HTTPException(409, 'Исходный файл изменился после подготовки патча')
        new_storage = str(uuid4())
        (DATA / new_storage).write_text(fix.data['after'], encoding='utf-8', newline='')
        file.data = {**file.data, 'storage': new_storage, 'size': len(fix.data['after'].encode())}
        fix.data = {**fix.data, 'applied': True, 'original_storage': path.name}
        db.commit()
        return serialize(fix)

@app.get('/api/exports')
def exports(project_id: UUID, format: Literal['feature', 'py', 'js', 'junit', 'ci'] = 'feature', run_id: UUID | None = None):
    with Session() as db:
        project_or_404(db, project_id)
        if format == 'junit':
            from apps.api.ci_exports import export_junit
            return Response(export_junit(db,str(project_id),run_id),media_type='application/xml',headers={'Content-Disposition':'attachment; filename="debugych-junit.xml"'})
        rows = db.scalars(select(Record).where(Record.project_id == str(project_id), Record.kind == 'test')).all()
        if format == 'ci':
            from apps.api.ci_exports import export_ci
            return Response(export_ci(rows),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="debugych-ci.zip"'})
        values = [r.data['gherkin'] if format == 'feature' else r.data['code'] for r in rows if format == 'feature' or r.data['framework'] == ('pytest' if format == 'py' else 'playwright')]
        if not values:
            raise HTTPException(404, 'Нет сценариев для выбранного формата')
        return Response('\n\n'.join(values), media_type='text/plain; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="debugych.{format}"'})

@app.get('/api/projects/{pid}/source-archive')
def source_archive(pid: UUID):
    import io,zipfile
    from apps.api.uploads import valid_name
    with Session() as db:
        project_or_404(db,pid)
        rows=db.scalars(select(Record).where(Record.project_id==str(pid),Record.kind=='file')).all()
        if not rows:
            raise HTTPException(404,'Нет файлов проекта')
        payload=io.BytesIO()
        names=set()
        with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as archive:
            for row in rows:
                name=row.data['name']; valid_name(name)
                if name in names:
                    raise HTTPException(409,'Дублирующиеся пути: создайте проект с однозначным набором файлов')
                names.add(name)
                archive.writestr(name,(DATA / row.data['storage']).read_bytes())
        return Response(payload.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="debugych-project.zip"'})

@app.get('/api/projects/{pid}/{resource}')
def records(pid: UUID, resource: Literal['files', 'requirements', 'test-cases', 'runs', 'fixes']):
    kinds = {'files': 'file', 'requirements': 'requirement', 'test-cases': 'test', 'runs': 'run', 'fixes': 'fix'}
    with Session() as db:
        project_or_404(db, pid)
        return [{k: v for k, v in serialize(r).items() if k not in ('storage','snapshot')} for r in db.scalars(select(Record).where(Record.project_id == str(pid), Record.kind == kinds[resource]).order_by(Record.created_at, Record.id))]

