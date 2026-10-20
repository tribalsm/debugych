"""The supervisor accepts data, never commands, images, mounts or Docker options."""
import hashlib
import json
from pathlib import PurePosixPath
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class SourceFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=300000)

    @model_validator(mode='after')
    def safe_path(self):
        path = PurePosixPath(self.path)
        if (path.is_absolute() or '\\' in self.path or ':' in self.path
            or any(part in ('', '.', '..') or part.startswith('.') for part in self.path.split('/'))
            or any(ord(c) < 32 for c in self.path) or '\x00' in self.content
            or path.suffix.lower() not in {'.py','.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css','.json'}):
            raise ValueError('Only safe relative source paths are accepted')
        return self

class GeneratedTest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    code: str = Field(min_length=1, max_length=16000)
    requirement_id: UUID

class SandboxJob(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    profile: Literal['playwright'] | None = None
    phase: Literal['validate'] | None = None
    expected_image_id: str | None = Field(default=None,pattern=r'^sha256:[0-9a-f]{64}$')
    files: list[SourceFile] = Field(min_length=1, max_length=100)
    tests: list[GeneratedTest] = Field(min_length=1, max_length=40)

    @model_validator(mode='after')
    def limits(self):
        allowed = {'.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css','.json'} if self.profile=='playwright' else {'.py'}
        if any(PurePosixPath(f.path).suffix.lower() not in allowed for f in self.files):
            raise ValueError('Source language does not match runner profile')
        if self.profile=='playwright' and not any(f.path=='index.html' for f in self.files):
            raise ValueError('Playwright profile requires index.html at project root')
        paths = [f.path.casefold() for f in self.files]
        ids = [str(t.id) for t in self.tests]
        if len(set(paths)) != len(paths) or len(set(ids)) != len(ids):
            raise ValueError('Duplicate file paths or test IDs')
        if sum(len(f.content.encode()) for f in self.files) + sum(len(t.code.encode()) for t in self.tests) > 2000000:
            raise ValueError('Snapshot exceeds 2 MB')
        return self

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.model_dump(mode='json',exclude_none=True),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class CaseResult(BaseModel):
    name: str = Field(max_length=300)
    test_id: UUID
    classname: str = Field(default='',max_length=400)
    status: Literal['passed','failed','error','skipped']
    traceback: str = Field(default='',max_length=12000)
    duration: float = Field(default=0,ge=0,le=120)

class CoverageTotals(BaseModel):
    percent_covered: float = Field(ge=0,le=100)
    covered_lines: int = Field(ge=0,le=1000000)
    num_statements: int = Field(ge=0,le=1000000)
    covered_branches: int = Field(default=0,ge=0,le=1000000)
    num_branches: int = Field(default=0,ge=0,le=1000000)

class CoverageFile(BaseModel):
    executed_lines: list[int] = Field(max_length=100000)
    missing_lines: list[int] = Field(max_length=100000)

class CoverageResult(BaseModel):
    totals: CoverageTotals
    files: dict[str,CoverageFile]

class DiscoveryItem(BaseModel):
    model_config=ConfigDict(extra='forbid')
    test_id: UUID
    name: str = Field(min_length=1,max_length=300)

class TechnicalValidation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    syntax: bool
    discovery: bool
    kind: Literal['valid','syntax_error','invalid_test']
    collected: list[DiscoveryItem] = Field(max_length=1000)

class SandboxResult(BaseModel):
    status: Literal['completed','failed']
    failure_kind: str | None = Field(default=None,max_length=100)
    error: str | None = Field(default=None,max_length=1000)
    exit_code: int | None = None
    duration: float = Field(default=0,ge=0,le=120)
    passed: int = Field(default=0,ge=0,le=1000)
    failed: int = Field(default=0,ge=0,le=1000)
    errors: int = Field(default=0,ge=0,le=1000)
    skipped: int = Field(default=0,ge=0,le=1000)
    cases: list[CaseResult] = Field(max_length=1000)
    logs: str = Field(default='',max_length=24000)
    coverage: CoverageResult | None = None
    coverage_kind: str | None = Field(default=None,max_length=80)
    artifacts: list['Artifact'] = Field(default_factory=list,max_length=10)
    validation: TechnicalValidation | None = None

class Artifact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(pattern=r'^[a-zA-Z0-9_-]+\.(png|json)$',max_length=120)
    media_type: Literal['image/png','application/json']
    data: str = Field(max_length=560000)
    test_id: UUID | None = None
    case_name: str | None = Field(default=None,max_length=300)

    @model_validator(mode='after')
    def valid_content(self):
        import base64
        raw=base64.b64decode(self.data,validate=True)
        if not raw or len(raw)>400000:
            raise ValueError('Artifact exceeds limit')
        if self.media_type=='image/png':
            if not self.name.endswith('.png') or len(raw)<45 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Invalid PNG artifact')
            import struct
            width,height=struct.unpack('>II',raw[16:24])
            if not 0<width<=4096 or not 0<height<=4096:
                raise ValueError('Oversized PNG dimensions')
            import zlib
            offset=8
            chunks=0
            while offset<len(raw):
                if offset+12>len(raw):
                    raise ValueError('Truncated PNG')
                size=struct.unpack('>I',raw[offset:offset+4])[0]
                end=offset+12+size
                if end>len(raw) or chunks>10000:
                    raise ValueError('Invalid PNG chunk')
                if zlib.crc32(raw[offset+4:end-4])!=struct.unpack('>I',raw[end-4:end])[0]:
                    raise ValueError('Invalid PNG checksum')
                kind=raw[offset+4:offset+8]
                if chunks==0 and (kind!=b'IHDR' or size!=13):
                    raise ValueError('Missing PNG header')
                offset=end; chunks+=1
                if kind==b'IEND':
                    if size or end!=len(raw):
                        raise ValueError('Invalid PNG ending')
                    break
            if not chunks or kind!=b'IEND':
                raise ValueError('Missing PNG ending')
        else:
            if not self.name.endswith('.json'):
                raise ValueError('Invalid report extension')
            json.loads(raw)
        return self

SandboxResult.model_rebuild()
