"""Bounded data-only artifacts. No HTML/JS from uploaded projects is served."""
import base64
import hashlib
import os
from pathlib import Path
from uuid import uuid4
from services.runner.contracts import Artifact

def directory():
    return Path(os.getenv('DATA_DIR','./data')) / 'artifacts'

def persist(result):
    values=[]
    directory().mkdir(parents=True,exist_ok=True)
    for raw in result.get('artifacts',[]):
        artifact=Artifact.model_validate(raw)
        content=base64.b64decode(artifact.data,validate=True)
        identity=str(uuid4())
        with (directory() / identity).open('xb') as stream:
            stream.write(content)
        values.append({'id':identity,'name':artifact.name,'media_type':artifact.media_type,
                       'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),
                       'test_id':str(artifact.test_id) if artifact.test_id else None,'case_name':artifact.case_name})
    return {**result,'artifacts':values}

def find(result,identity):
    for value in [result,*[result[k] for k in ('replay','baseline','focused','regression') if isinstance(result.get(k),dict)]]:
        for artifact in value.get('artifacts',[]):
            if artifact.get('id')==identity:
                return artifact
    return None
