"""Execution is restricted to the immutable, trusted shop fixture.

No uploaded code, test text, commands, paths or dependencies are accepted.
This is NOT an arbitrary-code sandbox.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'demo' / 'sample-python-app'
app = FastAPI(title='DEBUGYCH trusted runner')

class Task(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fixed: bool = False

def execute(fixed=False):
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='debugych-') as directory:
        target = Path(directory)
        for name in ['shop.py', 'test_shop.py']:
            shutil.copyfile(FIXTURE / name, target / name)
        if fixed:
            path = target / 'shop.py'
            path.write_text(path.read_text(encoding='utf-8').replace('return balance > amount', 'return balance >= amount'), encoding='utf-8')
        env = {key: os.environ[key] for key in ['PATH', 'SYSTEMROOT', 'TEMP', 'TMP'] if key in os.environ}
        env.update({'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8'})
        result = subprocess.run([sys.executable, '-m', 'coverage', 'run', '--branch', '--source=shop', '-m', 'pytest', '-q', '--junitxml=result.xml'], cwd=target, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, env=env)
        coverage_result = subprocess.run([sys.executable, '-m', 'coverage', 'json', '-o', 'coverage.json'], cwd=target, capture_output=True, timeout=10, env=env)
        if result.returncode not in (0, 1) or not (target / 'result.xml').exists() or coverage_result.returncode:
            raise RuntimeError('Runner infrastructure failure: ' + result.stdout[-4000:] + result.stderr[-4000:])
        tree = ET.parse(target / 'result.xml')
        cases = []
        for case in tree.iter('testcase'):
            failure = case.find('failure')
            error = case.find('error')
            skipped = case.find('skipped')
            cases.append({'name': case.attrib['name'], 'status': 'error' if error is not None else 'failed' if failure is not None else 'skipped' if skipped is not None else 'passed', 'traceback': failure.text if failure is not None else error.text if error is not None else '', 'duration': float(case.attrib.get('time', 0))})
        coverage = json.loads((target / 'coverage.json').read_text())
        return {'status': 'completed', 'duration': round(time.monotonic() - start, 3), 'passed': sum(c['status'] == 'passed' for c in cases), 'failed': sum(c['status'] == 'failed' for c in cases), 'cases': cases, 'coverage': coverage, 'logs': result.stdout[-20000:] + result.stderr[-4000:], 'fixed': fixed, 'trusted_demo': True}

@app.post('/execute')
def run(task: Task):
    return execute(task.fixed)

@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'trusted-demo-only'}
