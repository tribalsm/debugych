"""Authenticated data-only transport. Never executes submitted Python locally."""
import os
from pathlib import Path
import httpx
from services.runner.contracts import SandboxJob, SandboxResult

def execute(snapshot):
    if os.getenv('SANDBOX_ENABLED')!='1':
        raise ValueError('gVisor sandbox is not enabled')
    job=SandboxJob.model_validate(snapshot)
    token=Path(os.environ['RUNNER_TOKEN_FILE']).read_text().strip() if os.getenv('RUNNER_TOKEN_FILE') else os.getenv('RUNNER_TOKEN','')
    if len(token)<32:
        raise ValueError('Runner control credential is missing')
    response=httpx.post(os.getenv('SUPERVISOR_URL','http://127.0.0.1:8091')+'/execute',json=job.model_dump(mode='json',exclude_none=True),headers={'Authorization':'Bearer '+token},timeout=80,trust_env=False)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        try:
            detail=response.json().get('detail',response.reason_phrase)
        except (ValueError,AttributeError):
            detail=response.reason_phrase
        raise ValueError('gVisor Runner: '+str(detail)[:1000]) from error
    result=response.json()
    SandboxResult.model_validate(result)
    if result.get('snapshot_sha256')!=job.fingerprint() or result.get('runtime') not in (None,'runsc'):
        raise ValueError('Runner result does not match the submitted snapshot/runtime')
    if job.expected_image_id and result.get('image_id')!=job.expected_image_id:
        raise ValueError('Runner used a different sandbox image')
    if result.get('status')=='completed' and result.get('runtime')!='runsc':
        raise ValueError('A completed uploaded run must use runsc')
    from apps.api.run_artifacts import persist
    return persist(result)

