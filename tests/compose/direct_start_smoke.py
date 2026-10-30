"""Acceptance check on a disposable GitHub-hosted Linux runner, without an overlay.

Starts the literal foreground command from the case, then checks real imported
Python and Playwright tests. Never installs a runtime or contacts an LLM.
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'direct-compose-evidence'


def main():
    if os.getenv('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run only on the disposable GitHub Actions runner, not a shared Docker host')
    identity = os.environ.get('GITHUB_RUN_ID', '')
    if not re.fullmatch(r'\d+', identity):
        raise SystemExit('A GitHub run ID is required to scope cleanup')
    env = os.environ.copy()
    for key in ('COMPOSE_FILE', 'COMPOSE_PROFILES', 'COMPOSE_ENV_FILES'):
        env.pop(key, None)
    env.update(COMPOSE_PROJECT_NAME='debugych-direct-' + identity, LLM_API_KEY='',
               API_BASE='http://127.0.0.1:8000')
    OUT.mkdir(exist_ok=True)

    def run(*args, timeout=60):
        return subprocess.run(args, cwd=ROOT, env=env, check=True,
                              capture_output=True, text=True, timeout=timeout).stdout

    for port in (8000, 8080):
        with socket.socket() as connection:
            connection.settimeout(.5)
            assert connection.connect_ex(('127.0.0.1', port)) != 0, 'Foreign listener on ' + str(port)
    assert not run('docker-compose', 'ps', '-aq').strip(), 'Project already exists; refusing to reuse it'
    config = json.loads(run('docker-compose', 'config', '--format', 'json'))
    assert set(config['services']) == {'token-init', 'postgres', 'redis', 'api', 'worker',
                                     'runner', 'web', 'sandbox-image', 'playwright-image', 'supervisor'}
    assert config['services']['api']['environment']['LLM_API_KEY'] == ''
    assert config['services']['worker']['environment']['LLM_API_KEY'] == ''
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    command = ['docker-compose', 'up', '--build']
    summary = {'command': command, 'compose_file': 'docker-compose.yml', 'overlays': [],
               'llm_requests': 0, 'patch_applications': 0, 'status': 'failed'}
    started = time.monotonic()
    process = None
    try:
        with (OUT / 'foreground.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            deadline = started + 900
            while True:
                assert process.poll() is None, 'Foreground Compose stopped before readiness'
                assert time.monotonic() < deadline, 'Direct Compose readiness deadline exceeded'
                try:
                    with client.open('http://127.0.0.1:8000/api/health', timeout=3) as reply:
                        health = json.load(reply)
                    with client.open('http://127.0.0.1:8080/', timeout=3) as reply:
                        web = reply.status == 200 and b'<html' in reply.read().lower()
                    if web and health.get('sandbox_available') and health.get('playwright_available'):
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(2)
            assert health['execution'] == 'gvisor-python'
            assert not health['ai_available'], 'An external AI provider must not be available in this check'
            assert health['ai_provider_mode'] != 'contract-test', 'Test overlay unexpectedly active'
            supervisor = json.loads(run('docker-compose', 'exec', '-T', 'supervisor', 'python', '-c',
                "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8091/health'))))"))
            assert supervisor['runtime'] == 'runsc' and supervisor['playwright_image_id']
            imported = run(sys.executable, 'tests/compose/user_import_smoke.py', timeout=240)
            result = json.loads(imported.strip().splitlines()[-1])
            assert result['llm_requests'] == 0 and result['patch_applications'] == 0
            assert {r['profile']: r['passed'] for r in result['uploaded_tests']} == {'pytest': 2, 'playwright': 1}
            assert all(r['runtime'] == 'runsc' for r in result['uploaded_tests'])
            assert process.poll() is None, 'Compose exited during acceptance tests'
            summary.update(status='passed', uploaded_tests=result['uploaded_tests'], runtime='runsc',
                           no_llm_key=True, web_available=True, seconds=round(time.monotonic() - started, 2))
    finally:
        try:
            (OUT / 'services.log').write_text(run('docker-compose', 'logs', '--no-color'), encoding='utf-8')
        finally:
            # Unique project on a disposable runner. Never stop unrelated stacks.
            run('docker-compose', 'down', '--volumes', '--remove-orphans', timeout=90)
            if process is not None:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=15)
            (OUT / 'result.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
