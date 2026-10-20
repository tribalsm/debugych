"""Consent, persistent admission budget and metadata-only worker audit."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timezone
from urllib.parse import urlsplit
from sqlalchemy import select,update
from fastapi import HTTPException
from apps.api.db import Session,Record,AIBudget,add_record
from services.ai.adapter import AIAdapter,Settings,AIError
from services.ai.privacy import sanitize_files

active_adapter=ContextVar('ai_adapter',default=None)

def reserve(tokens,micro,settings):
    key=datetime.now(timezone.utc).date().isoformat()+':'+settings.mode
    with Session() as db:
        if db.bind.dialect.name=='postgresql':
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        db.execute(insert(AIBudget).values(id=key,calls=0,tokens=0,cost_micro=0).on_conflict_do_nothing(index_elements=['id']))
        result=db.execute(update(AIBudget).where(AIBudget.id==key,AIBudget.calls<settings.daily_calls,
            AIBudget.tokens+tokens<=settings.daily_tokens,AIBudget.cost_micro+micro<=round(settings.daily_usd*1000000))
            .values(calls=AIBudget.calls+1,tokens=AIBudget.tokens+tokens,cost_micro=AIBudget.cost_micro+micro))
        if result.rowcount!=1:
            db.rollback();raise AIError('daily_budget_exhausted')
        db.commit()

def texts(db,pid):
    from apps.api.jobs import DATA
    from apps.api.uploads import extract_text
    rows=db.scalars(select(Record).where(Record.project_id==pid,Record.kind=='file')).all()
    return sanitize_files([(r.data['name'],extract_text(r.data['name'],(DATA/r.data['storage']).read_bytes())) for r in rows])

def preview(db,pid):
    from apps.api.bug_workflow import state_hash
    from apps.api.jobs import DATA
    from services.ai.privacy import excluded,redact
    settings=Settings.load()
    manifest=[];characters=0
    for row in db.scalars(select(Record).where(Record.project_id==pid,Record.kind=='file')):
        name=row.data['name']
        if excluded(name):manifest.append({'name':name,'excluded':True,'redactions':0});continue
        if name.lower().endswith(('.pdf','.docx')):
            manifest.append({'name':name,'excluded':False,'redactions':None,'extraction':'async_in_worker'});continue
        content,count=redact((DATA/row.data['storage']).read_bytes().decode('utf-8-sig'))
        characters+=len(content)
        manifest.append({'name':name,'excluded':False,'redactions':count,'characters':len(content)})
    return {'project_state_sha256':state_hash(db,pid),'provider_fingerprint':settings.fingerprint(),
            'provider':urlsplit(settings.base_url).netloc,'model':settings.model,'manifest':manifest,
            'text_file_characters':characters,'max_job_usd_estimate':settings.job_usd,
            'notice':'Отправляются только очищенные тексты и данные выбранного workflow. Фильтр секретов эвристический; проверьте файлы перед согласием.'}

def consent(db,pid,value):
    from apps.api.bug_workflow import state_hash
    settings=Settings.load()
    if not value or not value.confirm:
        raise HTTPException(428,'Требуется отдельное согласие на передачу данных LLM-провайдеру')
    if value.project_state_sha256!=state_hash(db,pid) or value.provider_fingerprint!=settings.fingerprint():
        raise HTTPException(409,'Проект или настройки провайдера изменились; проверьте контекст и подтвердите отправку заново')
    return {**value.model_dump(),'granted_at':datetime.now(timezone.utc).isoformat()}

@contextmanager
def session(db,job):
    from apps.api.bug_workflow import state_hash
    settings=Settings.load()
    grant=job.data.get('ai_consent',{})
    if not grant.get('confirm') or grant.get('project_state_sha256')!=state_hash(db,job.project_id) or grant.get('provider_fingerprint')!=settings.fingerprint():
        raise AIError('consent_stale_or_missing')
    def audit(event):
        add_record(db,job.project_id,'ai_call',{'job_id':job.id,**event})
        db.commit()
    adapter=AIAdapter(settings,reserve=reserve,audit=audit)
    token=active_adapter.set(adapter)
    try:yield adapter
    finally:active_adapter.reset(token)

def current():return active_adapter.get() or AIAdapter()

def status():
    try:
        settings=Settings.load()
        return {'configured':bool(settings.key),'status':'ready' if settings.key else 'missing_LLM_API_KEY',
                'provider':urlsplit(settings.base_url).netloc,'model':settings.model,'mode':settings.mode,
                'provider_fingerprint':settings.fingerprint(),'response_format':settings.response_format,
                'max_job_tokens':settings.job_tokens,'max_job_usd_estimate':settings.job_usd,
                'daily_limits':{'calls':settings.daily_calls,'reserved_tokens':settings.daily_tokens,'reserved_usd_estimate':settings.daily_usd,'reset_timezone':'UTC'},
                'cost_basis':'conservative reservations at configured rates; not provider billing','live_verified':False}
    except AIError as error:return {'configured':False,'status':error.code,'live_verified':False}
