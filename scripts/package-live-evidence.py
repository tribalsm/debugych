"""Publish an allowlisted historical evidence view, not a new LLM execution.
Input: original outputs directory. No private oracle, provider prompts or credentials.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


def measurement(data):
    cases = data.get('cases', [])
    return {'passed': data.get('passed', sum(c['status'] == 'passed' for c in cases)),
            'failed': data.get('failed', sum(c['status'] == 'failed' for c in cases)),
            'errors': data.get('errors', sum(c['status'] == 'error' for c in cases)),
            'runtime': data['runtime'], 'status': data['status'],
            'snapshot_sha256': data.get('snapshot_sha256'),
            'cases': [{k: c.get(k) for k in ('name', 'status', 'traceback')} for c in cases]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    records = []
    for language, report, archive in [('Python', 'mvp-python-live.json', 'mvp-python-artifacts.zip'),
                                      ('JS/TS', 'autonomous-js.json', 'autonomous-js-artifacts.zip')]:
        raw = (args.source / report).read_bytes()
        value = json.loads(raw)
        result = value.get('results', [value])[0]
        assert result['autonomous'] and result['manual_interventions'] == 0 and not result['applied']
        assert result['mode'] == 'live' and result['tests_unchanged']
        workflow = result['workflow']
        calls = result['ai_statistics']['calls']
        assert all(c['mode'] == 'live' and c['model'] == 'gpt-6-luna' for c in calls)
        with zipfile.ZipFile(args.source / archive) as bundle:
            tests = [{'name': Path(n).name, 'code': bundle.read(n).decode('utf-8')}
                     for n in bundle.namelist() if n.startswith('unchanged-tests/')]
            original = measurement(json.loads(bundle.read('original/observations.json')))
            proof = measurement(json.loads(bundle.read('proof/observations.json')))
            candidate = measurement(json.loads(bundle.read('candidate/observations.json')))
            diff = bundle.read('candidate.diff').decode('utf-8')
        assert original['failed'] > 0 and proof['failed'] > 0 and candidate['failed'] == candidate['errors'] == 0
        attempts = workflow['validation']['attempts']
        scenarios = [s['gherkin'] for a in attempts for s in a.get('draft', {}).get('scenarios', [])]
        records.append({'language': language, 'model': 'gpt-6-luna', 'recorded_at': workflow['created_at'],
                        'autonomous': True, 'manual_interventions': 0, 'applied': False,
                        'report_sha256': hashlib.sha256(raw).hexdigest(),
                        'archive_sha256': hashlib.sha256((args.source / archive).read_bytes()).hexdigest(),
                        'original': original, 'proof': proof, 'candidate': candidate,
                        'tests': tests, 'gherkin': scenarios, 'diff': diff,
                        'calls': [{k: c.get(k) for k in ('operation', 'outcome', 'error_code', 'model')} for c in calls],
                        'requests': len(calls), 'failed_requests': sum(c['outcome'] == 'failed' for c in calls),
                        'billed_usd': None})
    payload = json.dumps({'version': 1, 'scope': 'historical-live-controls-2026-10-20',
                          'notice': 'Сохранённые настоящие live-прогоны, не новый запуск. Модель указана по метаданным настроенного стороннего провайдера. Эти контролируемые примеры не доказывают универсальную надёжность.',
                          'history_notice': 'До этих успешных записей две Python workflow-попытки завершились ошибками протокола. История ограничений сохранена в docs/archive/mvp-readiness.md. Новая RAG-версия платной LLM заново не проверялась.',
                          'records': records}, ensure_ascii=False, indent=2)
    assert not re.search(r'sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9_-]{20,}|PRIVATE KEY|LLM_API_KEY\s*=', payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding='utf-8')
    print(json.dumps({'records': len(records), 'requests_historical': sum(r['requests'] for r in records), 'new_llm_calls': 0}))


if __name__ == '__main__':
    main()
