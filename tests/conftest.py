"""Never let tests connect to a developer's database or configured LLM."""
import os
import tempfile
from pathlib import Path
import pytest

temporary=tempfile.TemporaryDirectory(prefix='debugych-tests-')
os.environ['DATABASE_URL']='sqlite:///'+(Path(temporary.name)/'test.db').as_posix()
os.environ['DATA_DIR']=str(Path(temporary.name)/'data')
os.environ['TASK_MODE']='local'
os.environ['SANDBOX_ENABLED']='0'
os.environ.pop('LLM_API_KEY',None)

@pytest.fixture(scope='session',autouse=True)
def isolated_test_environment():
    yield
    from apps.api.db import engine
    engine.dispose()
    temporary.cleanup()
