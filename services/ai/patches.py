"""Structured source replacements, validated again by the server; never raw patch execution."""
import json
import os
import httpx
from pydantic import BaseModel, ConfigDict, Field

class Replacement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    path: str = Field(min_length=1,max_length=200)
    before_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    content: str = Field(min_length=1,max_length=300000)

class PatchPlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    explanation: str = Field(min_length=1,max_length=3000)
    changes: list[Replacement] = Field(min_length=1,max_length=3)

def generate_patch(context):
    from apps.api.ai_runtime import current
    from services.ai.privacy import redact,excluded
    adapter=current()
    # Redacting implementation bytes would make replacements unsafe. Withhold
    # whole sensitive files; the model may propose changes only to sent paths.
    safe=[]
    allowed=('.js','.ts','.tsx','.jsx','.mjs','.cjs') if context.get('profile')=='playwright' else ('.py',)
    for source in context['files']:
        if source['path'].endswith(allowed) and not excluded(source['path']) and not redact(source['content'])[1]:safe.append(source)
    if not safe:
        from services.ai.adapter import AIError
        raise AIError('no_safe_patch_sources')
    context={**context,'files':safe}
    def validate(plan):
        if any(c.path not in {f['path'] for f in safe} for c in plan.changes):raise ValueError('Withheld source')
        return plan
    return adapter.generate('generate_patch',PatchPlan,
        'Prepare a minimal fix of the reviewed product behavior. Never change tests, assertions, requirements, dependencies, configuration or add files. '
        'Use the reviewed requirement, other documented_requirements and saved_suite_failures to avoid a partial fix that leaves other documented failures in the same suite. Requirements take precedence over generated assertions; do not invent behavior to satisfy an incorrect test. '
        'Failure diagnostics are explicitly bounded excerpts, not full test programs; all original tests remain immutable and will be used for verification. '
        'Return complete replacement contents of at most three existing implementation files with their supplied original SHA256. '
        'The runner profile is provided in context. Python syntax is validated locally as data; JS/TS syntax and behavior will be checked only in gVisor.',context,validate)
