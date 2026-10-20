"""Trusted read-only launcher. Imported from /opt with Python isolated mode.

Import instrumentation before adding the project path so uploaded pytest.py,
coverage.py or sitecustomize.py cannot replace our launcher at interpreter startup.
The test process and its outputs remain untrusted; only gVisor is a host boundary.
"""
import os
from pathlib import Path
import sys
import coverage
import pytest

project=Path('/tmp/job/project')
tests=Path('/tmp/job/tests')
reports=Path('/tmp/job/reports')
sys.path.append(str(project))
if os.getenv('DEBUGYCH_COLLECT_ONLY')=='1':
    import json
    class Collection:
        def pytest_collection_finish(self,session):
            (reports/'collection.json').write_text(json.dumps([{'file':Path(i.path).name,'name':i.name} for i in session.items]))
    code=pytest.main([str(tests),'-c','/opt/pytest.ini','--rootdir='+str(tests),'--confcutdir='+str(tests),'--collect-only','-q','-p','no:cacheprovider'],plugins=[Collection()])
    sys.exit(int(code))
cov=coverage.Coverage(data_file=str(reports / '.coverage'),source=[str(project)],branch=True,config_file=False)
cov.start()
try:
    code=pytest.main([str(tests),'-c','/opt/pytest.ini','--rootdir='+str(tests),'--confcutdir='+str(tests),'-q',
                      '--junitxml='+str(reports / 'results.xml'),'-p','no:cacheprovider'])
finally:
    cov.stop()
    cov.save()
    try:
        cov.json_report(outfile=str(reports / 'coverage.json'))
    except coverage.exceptions.CoverageException:
        pass
sys.exit(int(code))
