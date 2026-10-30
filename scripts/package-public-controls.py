"""Add measured, authored Python/TS controls to the read-only public snapshot."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('observations', type=Path)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    controls = json.loads(args.observations.read_text(encoding='utf-8-sig').split('PUBLIC_CONTROLS_JSON=')[-1])
    snapshot = json.loads(args.snapshot.read_text(encoding='utf-8'))
    routes = snapshot['routes']
    assert len(routes['/api/projects']) == 1, 'Start from the original one-project snapshot; do not append twice.'
    created = datetime.now(timezone.utc).isoformat()
    projects = []
    for control in controls:
        pid, bug_id, fix_id = (str(uuid4()) for _ in range(3))
        rid = control['requirement_id']
        prefix = '/api/projects/' + pid
        language = control['language']
        project = {'id': pid, 'name': language + ' · доставка и границы · gVisor', 'demo': False, 'created_at': created}
        requirement = {'id': rid, 'key': 'R1', 'text': 'Shipping is free when total is at least 500 cents. Below 500 cents shipping costs 60 cents.', 'source': 'requirements.md'}
        requirements = [requirement, {'id': str(uuid4()), 'key': 'R2', 'text': 'Negative amounts are rejected. Members pay 30 cents. These paths are intentionally not covered by this small demonstration suite.', 'source': 'requirements.md'}]
        original, proof, focused, regression = (control['observations'][k] for k in ('original', 'proof', 'focused', 'regression'))
        for phase, observation in control['observations'].items():
            files = [{**f, 'content': f['content'].replace('total > 500', 'total >= 500') if i == 0 and phase in ('focused', 'regression') else f['content']} for i, f in enumerate(control['source'])]
            payload = {'id': observation['id'], 'files': files, 'tests': [{'id': control['test_id'], 'requirement_id': rid, 'code': control['code']}]}
            if control['framework'] == 'playwright':
                payload['profile'] = 'playwright'
            if phase != 'original':
                payload['expected_image_id'] = original['image_id']
            # A runner fingerprint includes job ID and expected image. Compare
            # source/test digests separately, after binding the full real input.
            digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            assert digest(payload) == observation['snapshot_sha256'], phase
            observation['source_sha256'] = digest(files)
            observation['tests_sha256'] = digest(payload['tests'])
        assert original['failed'] == proof['failed'] == 1 and regression['failed'] == regression['errors'] == 0
        assert original['runtime'] == regression['runtime'] == 'runsc'
        failed = next(c for c in original['cases'] if c['status'] == 'failed')
        source = control['source'][0]
        fixed = source['content'].replace('total > 500', 'total >= 500')
        diff = ''.join(difflib.unified_diff(source['content'].splitlines(True), fixed.splitlines(True), fromfile='a/' + source['path'], tofile='b/' + source['path']))
        assessment = {'original_reproduced': True, 'original_fixed': True, 'regressions_absent': True, 'same_test_cases': True, 'tests_unchanged': True, 'full_correctness_proven': False, 'regression_cases_checked': max(0, regression['passed'] - 1)}
        baseline = {**original, 'operation': 'run', 'project_id': pid, 'created_at': created}
        replay = {**proof, 'operation': 'confirm_proof', 'project_id': pid, 'bug_id': bug_id, 'created_at': created, 'replay': proof}
        verification = {**regression, 'operation': 'verify', 'project_id': pid, 'fix_id': fix_id, 'created_at': created, 'verified': True, 'baseline': proof, 'focused': focused, 'regression': regression, 'assessment': assessment}
        runs = [baseline, replay, verification]
        filename = source['path']
        bug = {'id': bug_id, 'project_id': pid, 'title': 'Доставка платная при точной границе 500', 'framework': control['framework'], 'status': 'fix_verified', 'file': filename, 'line': 6 if language == 'Python' else 6,
               'requirement': 'R1', 'expected': 'shipping(500) returns 0 cents.', 'actual': 'shipping(500) returns 60 cents.', 'traceback': failed['traceback'], 'code': control['code'], 'run_id': original['id'], 'current_fix_id': fix_id,
               'description': 'Подготовленный контроль, не AI-генерация. Ожидание явно задано требованием R1. Падение повторено в отдельном gVisor-контейнере с тем же образом и неизменными тестами.',
               'steps': ['Открыть неизменный контрольный снимок.', 'Выполнить тест точной границы 500.', 'Сравнить 60 с ожидаемыми 0 центами.'], 'recommendation': 'Проверить включение границы в условие бесплатной доставки.', 'confirmation_basis': 'Документированный контроль R1; отдельное повторное assertion-падение в runsc. Это подготовленный пример, не новый LLM Bug Proof.'}
        fix = {'id': fix_id, 'project_id': pid, 'bug_id': bug_id, 'diff': diff, 'origin': 'prepared-demo', 'verified': True, 'applied': False, 'patch_sha256': hashlib.sha256(diff.encode()).hexdigest(), 'verification_id': regression['id'], 'assessment': assessment,
               'explanation': 'Подготовленный минимальный diff. Проверены кандидат и полный демонстрационный набор в двух отдельных gVisor-контейнерах. Исходные проекты не изменялись.'}
        test = {'id': control['test_id'], 'project_id': pid, 'requirement_id': rid, 'requirement_key': 'R1', 'title': 'Граница бесплатной доставки', 'framework': control['framework'], 'code': control['code'], 'origin': 'prepared-demo', 'status': 'validated',
                'gherkin': 'Feature: Shipping threshold\n  Scenario: Exact threshold\n    Given a non-member amount of 500 cents\n    When shipping is calculated\n    Then shipping costs 0 cents', 'test_sha256': control['test_sha256']}
        routes[prefix] = project
        routes[prefix + '/requirements'] = requirements
        routes[prefix + '/test-cases'] = [test]
        routes[prefix + '/files'] = [{'id': str(uuid4()), 'name': f['path'], 'size': len(f['content'].encode())} for f in control['source']] + [{'id': str(uuid4()), 'name': 'requirements.md', 'size': sum(len(r['text']) for r in requirements)}]
        routes[prefix + '/runs'] = runs
        routes[prefix + '/fixes'] = [fix]
        routes[prefix + '/ai-statistics'] = {'attempts': 0, 'succeeded': 0, 'failed': 0, 'reserved_tokens': 0, 'reserved_cost_micro_usd': 0, 'calls': [], 'notice': 'Подготовленные тесты. LLM не запускалась.'}
        routes['/api/bugs?project_id=' + pid] = [bug]
        for run in runs:
            routes['/api/runs/' + run['id']] = run
            routes['/api/runs/' + run['id'] + '/coverage'] = run['coverage']
            routes['/api/runs/' + run['id'] + '/artifacts'] = {k: run.get(k, [] if k != 'logs' else '') for k in ('logs', 'cases', 'artifacts')}
        routes['/api/bugs/' + bug_id] = bug
        projects.append(project)
    routes['/api/projects'] = projects + routes['/api/projects']
    snapshot['projectId'] = projects[0]['id']
    snapshot['notice'] = 'Подготовленные Python и TypeScript контроли с реальными сохранёнными gVisor-наблюдениями. Только просмотр, без новой AI-генерации. Исторические live AI-записи доступны отдельно на главной.'
    args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'new_projects': projects, 'llm_calls': 0, 'patches_applied': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
