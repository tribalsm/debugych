import os
import logging
from pathlib import Path
import httpx
from celery import Celery
from sqlalchemy import select
from apps.api.db import Session, Project, Record, add_record, serialize
from apps.api.uploads import extract_text
from services.ai.engine import TestGenerator, CodeAnalyzer, FailureAnalyzer, VerificationEngine

DATA = Path(os.getenv('DATA_DIR', './data'))
ROOT = Path(__file__).resolve().parents[2]
celery = Celery('debugych', broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
celery.conf.update(task_serializer='json', accept_content=['json'], task_soft_time_limit=240, task_time_limit=270, broker_connection_retry_on_startup=True)

def update(db, row, **data):
    row.data = {**row.data, **data}
    db.commit()

def run_uploaded(db, job):
    """Only send data to an external mandatory-gVisor supervisor."""
    from services.runner.contracts import SandboxJob
    if os.getenv('SANDBOX_ENABLED')!='1':
        raise ValueError('gVisor sandbox is not enabled')
    snapshot = SandboxJob.model_validate(job.data['snapshot'])
    update(db,job,status='running')
    from apps.api import sandbox_client
    result = sandbox_client.execute(snapshot.model_dump(mode='json',exclude_none=True))
    if result.get('status')=='completed':
        saved_tests = {str(test.id):test for test in snapshot.tests}
        for test_id, submitted in saved_tests.items():
            cases = [case for case in result['cases'] if case.get('test_id')==test_id]
            current = db.get(Record,test_id)
            # Never attribute an old result to code edited after submission.
            if current and current.data['code']==submitted.code:
                statuses = {case['status'] for case in cases}
                status = next((s for s in ['error','failed','passed','skipped'] if s in statuses),'not_run')
                current.data = {**current.data,'result':status,'last_run_id':job.id}
            requirement = db.get(Record,str(submitted.requirement_id))
            for case in cases:
                classification = FailureAnalyzer.classify(case, bool(requirement), False)
                if classification in ('reproduced','suspected'):
                    add_record(db,job.project_id,'bug',{'title':case['name'],'status':classification,'description':'AI-тест воспроизвёл отклонение. Ожидаемый результат требует независимой проверки; дефект автоматически не подтверждён.',
                               'requirement':requirement.data['key'] if requirement else '', 'requirement_id':str(submitted.requirement_id),
                               'run_id':job.id,'framework':'playwright' if snapshot.profile=='playwright' else 'pytest','file':'tests/test_'+test_id.replace('-','')+('.spec.ts' if snapshot.profile=='playwright' else '.py'),'line':None,
                               'expected':requirement.data['text'] if requirement else 'Проверить assertion теста',
                               'actual':case.get('traceback','')[-1500:],'traceback':case.get('traceback',''),'code':submitted.code,
                               'steps':['Открыть снимок запуска '+job.id,'Повторить тест в том же образе gVisor'],
                               'recommendation':'Проверьте, что assertion соответствует исходному требованию и ошибка относится к продукту.',
                               'snapshot_sha256':snapshot.fingerprint(),'test_id':test_id,'test_sha256':__import__('hashlib').sha256(submitted.code.encode()).hexdigest(),
                               'case_identity':[test_id,case.get('classname',''),case['name']],
                               'project_state_sha256':job.data.get('project_state_sha256')})
    from services.ai.quality import evaluate
    inputs=job.data.get('quality_inputs',{'requirement_ids':[],'tests':[]})
    quality=evaluate(inputs['requirement_ids'],inputs['tests'],result)
    update(db,job,**result,quality=quality,profile=snapshot.profile or 'python-pytest')

@celery.task(name='debugych.process')
def process(job_id):
    with Session() as db:
        job = db.get(Record, job_id)
        if not job or job.data['status'] == 'cancelled':
            return
        project = db.get(Project, job.project_id)
        try:
            operation = job.data['operation']
            if operation=='autonomous':
                from apps.api.autonomous import process_autonomous
                process_autonomous(db,job)
                return
            if operation == 'analyze':
                update(db, job, status='analyzing')
                files = db.scalars(select(Record).where(Record.project_id == project.id, Record.kind == 'file')).all()
                texts = [(f.data['name'], extract_text(f.data['name'], (DATA / f.data['storage']).read_bytes())) for f in files]
                from services.ai.privacy import sanitize_files
                _,manifest=sanitize_files(texts)
                job.data={**job.data,'privacy_manifest':manifest}
                summary = CodeAnalyzer.summarize(texts)
                update(db, job, status='generating')
                if project.demo:
                    from services.ai.engine import Plan
                    requirements = [{'key': f'R{i+1}', 'text': text.split('. ', 1)[-1]} for i, text in enumerate((ROOT / 'demo/sample-python-app/requirements.md').read_text(encoding='utf-8').splitlines()[1:])]
                    code = (ROOT / 'demo/sample-python-app/test_shop.py').read_text(encoding='utf-8')
                    plan = Plan(requirements=requirements, scenarios=[{'title': 'Границы оплаты, скидки и количества', 'requirement': 'R1', 'gherkin': 'Feature: Payment validation\n\nScenario: Exact available balance\n  Given account balance is 1000\n  When user pays 1000\n  Then payment is accepted\n', 'code': code, 'framework': 'pytest'}])
                else:
                    from apps.api.ai_runtime import session
                    with session(db,job) as adapter:
                        try:
                            plan = TestGenerator.generate(texts,adapter)
                        finally:
                            from services.ai.privacy import sanitize_value
                            update(db,job,generation_review=sanitize_value({
                                'acceptance_contract':getattr(adapter,'acceptance_contract',None),
                                'drafts':getattr(adapter,'review_drafts',[])}))
                    job.data={**job.data,'requirement_evidence':adapter.requirement_evidence}
                    from apps.api.bug_workflow import lock_project,state_hash
                    lock_project(db,project.id)
                    if state_hash(db,project.id)!=job.data['ai_consent']['project_state_sha256']:
                        raise ValueError('Проект изменился во время генерации; план не сохранён, нужен новый анализ с согласием')
                existing = db.scalars(select(Record).where(Record.project_id == project.id, Record.kind == 'test')).all()
                if existing:
                    raise ValueError('План уже существует. Создайте новый проект для повторного анализа; редактирование доступно в Test Studio.')
                reqs = {}
                evidence={r['key']:r for r in job.data.get('requirement_evidence',[])}
                for requirement in plan.requirements:
                    cited={k:evidence[requirement.key][k] for k in ('source','quote')} if requirement.key in evidence else {}
                    reqs[requirement.key] = add_record(db, project.id, 'requirement', {**requirement.model_dump(),**cited}).id
                for scenario in plan.scenarios:
                    add_record(db, project.id, 'test', {**scenario.model_dump(), 'requirement_id': reqs[scenario.requirement], 'origin': 'prepared-demo' if project.demo else 'llm-contract-test' if os.getenv('LLM_PROVIDER_MODE')=='contract-test' else 'llm', 'result': 'not_run'})
                update(db, job, status='completed', analysis=summary)
            else:
                if not project.demo:
                    if operation=='run':
                        run_uploaded(db,job)
                    else:
                        from apps.api.bug_workflow import proof_job,propose_job,verify_job
                        update(db,job,status='generating' if operation=='propose_fix' else 'running')
                        handler={'confirm_proof':proof_job,'propose_fix':propose_job,'verify':verify_job}.get(operation)
                        if not handler:
                            raise ValueError('Неизвестная операция')
                        if operation=='propose_fix':
                            from apps.api.ai_runtime import session
                            with session(db,job):handler(db,job)
                        else:handler(db,job)
                    return
                update(db, job, status='running')
                result = httpx.post(os.getenv('RUNNER_URL', 'http://127.0.0.1:8090') + '/execute', json={'fixed': operation == 'verify' or job.data.get('fixed', False)}, timeout=60)
                result.raise_for_status()
                payload = result.json()
                if operation == 'verify':
                    bug = db.get(Record, job.data['bug_id'])
                    original = db.get(Record, bug.data['run_id'])
                    assessment = VerificationEngine.assess(original.data, payload)
                    proposal = db.get(Record, job.data['fix_id'])
                    verified = assessment['original_fixed'] and assessment['regressions_absent']
                    update(db, proposal, verified=verified, verification_id=job.id, assessment=assessment)
                    if verified:
                        update(db, bug, status='fix_verified')
                    update(db, job, **payload, assessment=assessment)
                else:
                    tests = db.scalars(select(Record).where(Record.project_id == project.id, Record.kind == 'test')).all()
                    for test in tests:
                        test.data = {**test.data, 'result': 'failed' if payload['failed'] else 'passed'}
                    for case in payload['cases']:
                        if FailureAnalyzer.classify(case, bool(tests), True) == 'confirmed':
                            source_lines = (ROOT / 'demo/sample-python-app/shop.py').read_text(encoding='utf-8').splitlines()
                            source_line = next(i for i, line in enumerate(source_lines, 1) if 'return balance > amount' in line)
                            add_record(db, project.id, 'bug', {'title': 'Платёж отклонён при точном балансе', 'status': 'confirmed', 'description': 'Контрольный тест воспроизвёл нарушение R1. Доверенный тест и окружение известны.', 'requirement': 'R1', 'requirement_id': tests[0].data['requirement_id'], 'run_id': job.id, 'file': 'shop.py', 'line': source_line, 'expected': 'True — платёж принят', 'actual': 'False — платёж отклонён', 'traceback': case['traceback'], 'code': (ROOT / 'demo/sample-python-app/test_shop.py').read_text(encoding='utf-8'), 'steps': ['Баланс 1000', 'Вызвать pay(1000, 1000)', 'Сравнить результат с True'], 'recommendation': 'Проверьте включительную границу сравнения баланса.'})
                    update(db, job, **payload)
        except Exception as error:
            db.rollback()
            logging.error('Job %s failed: %s', job_id,type(error).__name__)
            job = db.get(Record, job_id)
            from services.ai.privacy import redact
            update(db, job, status='failed', error=redact(str(error))[0][:1500])

def dispatch(job_id, background):
    if os.getenv('TASK_MODE', 'local') == 'celery':
        process.delay(job_id)
    else:
        background.add_task(process, job_id)
