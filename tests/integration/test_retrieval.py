import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from apps.api.db import ContextChunk,Session
from apps.api.main import app
from apps.api.retrieval import index,search,generation_context
from services.ai.retrieval import chunks,encode,FALLBACK_ID
from services.ai.validation import ManualReview

def test_embeddings_are_local_and_fallback_is_explicit(monkeypatch,tmp_path):
    monkeypatch.setenv('RAG_EMBEDDINGS','local');monkeypatch.setenv('RAG_MODEL_DIR','/nonexistent-model')
    encoder,vectors=encode(['payment boundary','payment boundary'])
    assert encoder==FALLBACK_ID and vectors[0]==vectors[1] and len(vectors[0])==384
    import runpy,urllib.request,urllib.error,io
    from pathlib import Path
    prepare=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/prepare-embeddings.py'))['prepare']
    def offline(*args,**kwargs):raise urllib.error.URLError('offline test')
    monkeypatch.setattr(urllib.request,'urlopen',offline)
    prepare(tmp_path/'optional',optional=True)
    assert (tmp_path/'optional').is_dir()
    with pytest.raises(urllib.error.URLError):prepare(tmp_path/'required')
    monkeypatch.setattr(urllib.request,'urlopen',lambda *args,**kwargs:io.BytesIO(b'corrupt fixture'))
    with pytest.raises(ValueError,match='checksum'):prepare(tmp_path/'corrupt')
    assert not list((tmp_path/'corrupt').rglob('*.download'))
    from concurrent.futures import ThreadPoolExecutor
    from functools import lru_cache
    from threading import Barrier
    import sys,time
    from services.ai import retrieval
    loads=[];barrier=Barrier(2)
    def stop_before_inference(_):raise ValueError('controlled fallback after loading')
    @lru_cache(maxsize=2)
    def slow_model(directory):
        loads.append(directory);time.sleep(.05)
        return SimpleNamespace(encode_batch=stop_before_inference),None
    monkeypatch.setitem(sys.modules,'numpy',SimpleNamespace())
    monkeypatch.setattr(retrieval,'model',slow_model)
    def parallel_query():barrier.wait(timeout=5);return encode(['payment'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:parallel_query(),range(2)))
    assert len(loads)==1 and all(result[0]==FALLBACK_ID for result in results)

def test_chunks_preserve_lines_redact_and_exclude_private_oracles():
    files=[('requirements.md','R1. Payment accepted.\nR2. Reset.\n'),('app.py','API_KEY="super-private-value"\n'+'x'*2000),('.env','TOP_SECRET'),('oracles/test_private.py','RIGHT_PATCH')]
    parts=chunks(files);assert all(len(p['content'])<=900 for p in parts)
    assert all(p['path'] not in ('.env','oracles/test_private.py') for p in parts)
    assert 'super-private-value' not in json.dumps(parts) and '[REDACTED]' in json.dumps(parts)
    assert ''.join(p['content'] for p in parts if p['path']=='requirements.md')==files[0][1]
    assert all(p['start_line']<=p['end_line'] for p in parts)

def test_index_version_is_reused_refreshed_isolated_and_deleted():
    with TestClient(app) as client:
        a=client.post('/api/projects',json={'name':'A'}).json()['id'];b=client.post('/api/projects',json={'name':'B'}).json()['id']
        with Session() as db:
            metadata=index(db,a,[('charge.py','def payment(balance): return balance')])
            assert index(db,a,[('charge.py','def payment(balance): return balance')])['reused']
            index(db,b,[('hidden.py','payment secret project B')])
            found=search(db,a,'payment',metadata)
            assert found['mode']=='lexical-fallback' and [r['path'] for r in found['matches']]==['charge.py']
            new=index(db,a,[('reset.py','def reset(): return 0')]);assert new['version']!=metadata['version']
            assert search(db,a,'payment',metadata)['matches']==[]
        assert client.delete('/api/projects/'+a).status_code==200
        with Session() as db:assert not db.scalar(select(ContextChunk).where(ContextChunk.project_id==a))

def test_context_search_api_validates_input_and_redacts():
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    with Session() as db:
        with pytest.raises(DBAPIError) as failure:
            db.execute(text('SELECT content FROM nonexistent_privacy_probe WHERE content=:content'),{'content':'private-embedding-source-sentinel'})
        assert 'private-embedding-source-sentinel' not in str(failure.value)
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'Search'}).json()['id']
        client.post(f'/api/projects/{pid}/files',files={'file':('requirements.md',b'R1. Payment succeeds at exact balance.\nAPI_KEY="private-secret-123"')})
        # The free synchronous endpoint must not invoke binary document parsers.
        client.post(f'/api/projects/{pid}/files',files={'file':('unparsed.pdf',b'%PDF-intentionally-unparseable')})
        result=client.post(f'/api/projects/{pid}/context-search',json={'query':'payment balance'})
        assert result.status_code==200 and result.json()['mode']=='lexical-fallback'
        assert 'private-secret-123' not in result.text and result.json()['matches'][0]['path']=='requirements.md'
        assert result.json()['document_scope']=='source-and-markdown'
        assert client.post(f'/api/projects/{pid}/context-search',json={'query':'   '}).status_code==422
        assert client.post(f'/api/projects/{pid}/context-search',json={'query':'payment','limit':1000}).status_code==422

def test_generation_preserves_small_source_and_stops_when_large_context_cannot_be_grounded():
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'Generation context'}).json()['id']
        with Session() as db:
            files=[('requirements.md','R1. Payment accepted.'),('payment.py','def payment(): return True')]
            source,metadata=generation_context(db,pid,files,[SimpleNamespace(text='Payment accepted')])
            assert source==[{'path':'payment.py','content':'def payment(): return True'}]
            assert metadata['requirements_preserved'] and metadata['selection']=='full-source'
            files=[('requirements.md','R1. Authorization.'),('other.py',('nothing irrelevant\n'*1000))]
            with pytest.raises(ManualReview):generation_context(db,pid,files,[SimpleNamespace(text='authorization')])

def test_index_bounds_fail_before_expensive_embedding(monkeypatch):
    from apps.api import retrieval
    with TestClient(app) as client:
        pid=client.post('/api/projects',json={'name':'Index capacity'}).json()['id']
        monkeypatch.setattr(retrieval,'encode',lambda _:pytest.fail('Oversized index must not invoke embeddings'))
        with Session() as db:
            with pytest.raises(ValueError,match='160 chunks'):index(db,pid,[('large.py',('x'*899+'\n')*161)])

def test_search_admission_is_bounded_without_runner_changes():
    from apps.api.main import _retrieval_admission
    assert _retrieval_admission.acquire(blocking=False) and _retrieval_admission.acquire(blocking=False)
    try:
        with TestClient(app) as client:
            result=client.post('/api/projects/00000000-0000-4000-8000-000000000001/context-search',json={'query':'payment'})
            assert result.status_code==429
    finally:_retrieval_admission.release();_retrieval_admission.release()
