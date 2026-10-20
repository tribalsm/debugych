"""Runs INSIDE the disposable gVisor container. No infrastructure credentials.

Container filesystem is read-only except bounded /tmp tmpfs. All user code and
generated tests run as uid 10000. Reports are untrusted observations, not proof
of correctness or confirmation of an AI-generated assertion.
"""
import json
import ast
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

LIMIT = 1000000

def read_report(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > LIMIT:
        raise ValueError('Report missing, unsafe or oversized')
    return path.read_bytes()

def main():
    start = time.monotonic()
    # Limits inherited by pytest and any descendants; cgroups add aggregate limits.
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT, LIMIT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
    raw = sys.stdin.buffer.readline(8500000)
    if len(raw) >= 8500000 or not raw.endswith(b'\n'):
        raise ValueError('Invalid input envelope')
    job = json.loads(raw)
    if job.get('phase')=='validate':
        try:
            for item in [*job['files'],*job['tests']]:ast.parse(item['content'] if 'content' in item else item['code'])
        except SyntaxError:
            return {'status':'completed','cases':[],'validation':{'syntax':False,'discovery':False,'kind':'syntax_error','collected':[]}}
    root = Path('/tmp/job')
    project, tests, reports = root / 'project', root / 'tests', root / 'reports'
    for directory in [project, tests, reports]:
        directory.mkdir(parents=True)
    # Supervisor validates names before delivery; enforce traversal defense again.
    for source in job['files']:
        path = project / source['path']
        if not path.resolve().is_relative_to(project):
            raise ValueError('Unsafe path')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source['content'],encoding='utf-8')
    test_ids = {}
    for test in job['tests']:
        filename = 'test_' + str(test['id']).replace('-','') + '.py'
        (tests / filename).write_text(test['code'],encoding='utf-8')
        test_ids[filename] = str(test['id'])
    env = {'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','TMPDIR':'/tmp','LANG':'C.UTF-8',
           'PYTHONPATH':str(project),'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
           'COVERAGE_FILE':str(reports / '.coverage')}
    command = [sys.executable,'-I','/opt/pytest_bootstrap.py']
    if job.get('phase')=='validate':env['DEBUGYCH_COLLECT_ONLY']='1'
    with (reports / 'pytest.log').open('wb') as log:
        result = subprocess.run(command,cwd='/tmp',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    log = read_report(reports / 'pytest.log').decode('utf-8',errors='replace')[-24000:]
    if job.get('phase')=='validate':
        collection=json.loads(read_report(reports/'collection.json')) if (reports/'collection.json').is_file() else []
        collected=[{'test_id':test_ids.get(item['file']),'name':item['name']} for item in collection]
        valid=result.returncode==0 and bool(collected) and all(c['test_id'] for c in collected)
        return {'status':'completed','cases':[],'logs':log,'validation':{'syntax':True,'discovery':valid,'kind':'valid' if valid else 'invalid_test','collected':collected}}
    if result.returncode not in (0, 1):
        return {'status':'failed','failure_kind':'test_collection_or_infrastructure','exit_code':result.returncode,'logs':log,'cases':[]}
    tree = ET.fromstring(read_report(reports / 'results.xml'))
    cases = []
    for suite in tree.iter('testcase'):
        failure,error,skipped = suite.find('failure'),suite.find('error'),suite.find('skipped')
        classname = suite.get('classname','')
        test_id = next((v for k,v in test_ids.items() if k[:-3] in classname),None)
        cases.append({'name':suite.get('name','')[:300],'test_id':test_id,'classname':classname[:400],
                      'status':'error' if error is not None else 'failed' if failure is not None else 'skipped' if skipped is not None else 'passed',
                      'traceback':((failure.text if failure is not None else error.text if error is not None else '') or '')[:12000],
                      'duration':float(suite.get('time','0'))})
        if len(cases) > 1000:
            raise ValueError('Too many result cases')
    coverage = json.loads(read_report(reports / 'coverage.json')) if (reports / 'coverage.json').is_file() else None
    if coverage:
        # Drop verbose function/class details; only expose paths relative to the project.
        coverage['files'] = {str((Path('/tmp') / name).relative_to(project)) if (Path('/tmp') / name).is_relative_to(project) else name:
                             {key:value for key,value in data.items() if key not in ('functions','classes')}
                             for name,data in coverage['files'].items()}
    return {'status':'completed','exit_code':result.returncode,'duration':round(time.monotonic()-start,3),
            'passed':sum(c['status']=='passed' for c in cases),'failed':sum(c['status']=='failed' for c in cases),
            'errors':sum(c['status']=='error' for c in cases),'skipped':sum(c['status']=='skipped' for c in cases),
            'cases':cases,'logs':log,'coverage':coverage,'trusted_demo':False,'report_trust':'untrusted-project-observation'}

if __name__ == '__main__':
    try:
        result = main()
    except Exception as error:
        result = {'status':'failed','failure_kind':'harness_or_infrastructure','error':str(error)[:1000],'cases':[]}
    print('DEBUGYCH_RESULT='+json.dumps(result,ensure_ascii=True),flush=True)
