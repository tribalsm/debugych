"""Data-only CI exports. No uploaded code is evaluated by this module."""
import hashlib
import io
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from fastapi import HTTPException
from sqlalchemy import select
from apps.api.db import Record


def xml_text(value):
    return ''.join(c for c in str(value) if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)


def junit(run):
    if run.get('status') not in ('completed', 'failed'):
        raise HTTPException(409, 'Дождитесь завершения запуска')
    operation = run.get('operation')
    if operation not in ('run', 'verify'):
        raise HTTPException(422, 'JUnit доступен для запуска тестов или регрессии исправления')
    data = run if operation == 'run' else run.get('regression')
    # Legacy prepared-demo verification stored only the final regression payload.
    if operation == 'verify' and data is None and isinstance(run.get('assessment'), dict) and isinstance(run.get('cases'), list):
        data = run
    if not isinstance(data, dict):
        raise HTTPException(409, 'Отчёт регрессии ещё не получен')
    cases = data.get('cases', [])
    if not isinstance(cases, list) or len(cases) > 1000:
        raise HTTPException(422, 'Некорректный список результатов')
    counts = dict.fromkeys(('passed', 'failed', 'errors', 'skipped'), 0)
    root = ET.Element('testsuites')
    suite = ET.SubElement(root, 'testsuite', name='Debugych regression' if operation == 'verify' else 'Debugych tests')
    properties = ET.SubElement(suite, 'properties')
    for key, value in {'run_id': run.get('id', ''), 'operation': operation, 'scope': 'regression' if operation == 'verify' else 'test-set', 'runtime': data.get('runtime', '')}.items():
        ET.SubElement(properties, 'property', name=key, value=xml_text(value))
    duration = 0.0
    for case in cases:
        if not isinstance(case, dict) or case.get('status') not in ('passed', 'failed', 'error', 'skipped'):
            raise HTTPException(422, 'Неизвестный результат теста')
        status = case['status']; counts['errors' if status == 'error' else status] += 1
        seconds = case.get('duration', 0)
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
            raise HTTPException(422, 'Некорректная длительность теста')
        duration += seconds
        node = ET.SubElement(suite, 'testcase', name=xml_text(case.get('name', 'unnamed')), classname=xml_text(case.get('classname', '')), time=f'{seconds:.6f}')
        if status != 'passed':
            child = ET.SubElement(node, {'failed': 'failure', 'error': 'error', 'skipped': 'skipped'}[status], message=status)
            child.text = xml_text(case.get('traceback', ''))[:12000]
    invalid = any(key in data and (type(data[key]) is not int or data[key] != value) for key, value in counts.items())
    # A crashed runner with partial results must never become a green CI check.
    if run['status'] == 'failed' or data.get('status') == 'failed' or invalid or not cases:
        node = ET.SubElement(suite, 'testcase', name='Debugych execution integrity', classname='debugych.infrastructure', time='0')
        ET.SubElement(node, 'error', message='Incomplete or inconsistent execution report').text = 'Runner failed, returned no cases, or summary does not match the case results.'
        counts['errors'] += 1
    attributes = {'tests': str(sum(counts.values())), 'failures': str(counts['failed']), 'errors': str(counts['errors']), 'skipped': str(counts['skipped']), 'time': f'{duration:.6f}'}
    suite.attrib.update(attributes); root.attrib.update(attributes)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def export_junit(db, pid, run_id=None):
    query = select(Record).where(Record.project_id == pid, Record.kind == 'run')
    if run_id:
        row = db.scalar(query.where(Record.id == str(run_id)))
        if row is None: raise HTTPException(404, 'Запуск не найден в этом проекте')
    else:
        rows = db.scalars(query.order_by(Record.created_at.desc(), Record.id.desc())).all()
        row = next((r for r in rows if r.data.get('operation') == 'run' and r.data.get('status') in ('completed', 'failed')), None)
        if row is None: raise HTTPException(404, 'Нет завершённого запуска тестов')
    return junit({**row.data, 'id': row.id})


WORKFLOW = '''name: Debugych QA
on: workflow_dispatch
permissions:
  contents: read
jobs:
  qa:
    runs-on: ubuntu-latest
    timeout-minutes: 12
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Execute frozen tests in remote gVisor
        env:
          DEBUGYCH_BASE_URL: ${{ vars.DEBUGYCH_BASE_URL }}
          DEBUGYCH_USERNAME: ${{ secrets.DEBUGYCH_USERNAME }}
          DEBUGYCH_PASSWORD: ${{ secrets.DEBUGYCH_PASSWORD }}
        run: python debugych_ci/run.py --root . --output debugych-report
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: debugych-results
          path: debugych-report/
'''


def export_ci(rows):
    if not rows: raise HTTPException(404, 'Нет тестов для экспорта')
    frameworks = {r.data.get('framework') for r in rows}
    if len(rows) > 40 or len(frameworks) != 1 or not frameworks <= {'pytest', 'playwright'}:
        raise HTTPException(422, 'Экспортируйте до 40 модулей одного framework')
    framework = next(iter(frameworks)); files = {}; entries = []
    for row in rows:
        code = row.data.get('code', '')
        if not isinstance(code, str) or not code.strip() or len(code) > 16000:
            raise HTTPException(422, 'Некорректный модуль тестов')
        name = 'debugych_ci/tests/' + ('test_' + row.id + '.py' if framework == 'pytest' else row.id + '.spec.ts')
        payload = code.encode('utf-8'); files[name] = payload
        entries.append({'path': name, 'sha256': hashlib.sha256(payload).hexdigest()})
    files['debugych_ci/plan.json'] = json.dumps({'version': 1, 'framework': framework, 'tests': entries}, indent=2).encode()
    files['debugych_ci/run.py'] = Path(__file__).with_name('ci_client.py').read_bytes()
    files['.github/workflows/debugych-qa.yml'] = WORKFLOW.encode()
    files['debugych_ci/README.md'] = '''# Debugych CI

Review the exported tests before committing this package. They are frozen code,
not a claim that every requirement has been tested. Existing CI remains necessary.

Set repository variable DEBUGYCH_BASE_URL to the HTTPS root of your Debugych server.
Set secrets DEBUGYCH_USERNAME and DEBUGYCH_PASSWORD for a dedicated ordinary account.
Enable Actions and start Debugych QA manually (workflow_dispatch).
Never use an administrator account, owner token, or LLM API key.

The client uploads the checked-out source and these exact test modules to a temporary
private project, imports selected tests, and executes them in the server's gVisor.
No uploaded code executes on the GitHub runner. No AI requests or patches are made.
The temporary project is deleted after execution. Cleanup may fail if the server is
unreachable or a task is still running; remove the named CI project later in that case.
JUnit XML and JSON are saved as workflow artifacts. A failing assertion, infrastructure
failure, missing report, or all-skipped suite fails the job. This is not coverage for
tests that were not exported. Verify results export regression only, not the expected
failing baseline.

Source upload is intentional: use only a trusted server. Hidden files, symlinks,
dependency/build directories and common credential filenames are excluded. Inspect
the archive list with --list-files before sending proprietary code. Secret detection
cannot guarantee removal of secrets embedded in arbitrary source files.
Fixed sandbox dependencies, account quotas and runner limits still apply.
'''.encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items(): archive.writestr(name, payload)
    return buffer.getvalue()
