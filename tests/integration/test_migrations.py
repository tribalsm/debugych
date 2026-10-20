import os
import subprocess
import sys
from sqlalchemy import create_engine, inspect

def test_alembic_upgrade_downgrade(tmp_path):
    url = 'sqlite:///' + (tmp_path / 'migrations.db').as_posix()
    env = {**os.environ, 'DATABASE_URL':url}
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True,capture_output=True)
    engine = create_engine(url)
    try:
        assert {'projects','records','alembic_version'} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    subprocess.run([sys.executable,'-m','alembic','downgrade','base'],env=env,check=True,capture_output=True)
    engine = create_engine(url)
    try:
        assert 'projects' not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
