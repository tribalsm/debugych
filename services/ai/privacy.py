"""Best-effort secret removal before external transport; never log matched text."""
import os
import re
from pathlib import PurePosixPath

PATTERNS=[
    r'\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{15,}|AKIA[A-Z0-9]{16})\b',
    r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b',
    r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}',
    r'''(?im)(?<![\w-])["']?[\w-]{0,80}(?:api[_-]?key|secret|password|passwd|token|database_url)[\w-]{0,80}["']?\s*[:=]\s*["'][^"'\r\n]+["']''',
    r'(?im)\b(?:API_KEY|SECRET|SECRET_KEY|PASSWORD|TOKEN|ACCESS_TOKEN|AUTH_TOKEN|DATABASE_URL)\s*=\s*[^\s\r\n]+',
    r'(?i)\b[a-z][a-z0-9+.-]{0,20}://[^\s/:]+:[^\s/@]+@[^\s"\'<>]+',
]

def redact(text):
    count=0
    while True:
        start=re.search(r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----',text)
        if not start:break
        end=re.search(r'-----END (?:[A-Z ]+ )?PRIVATE KEY-----',text[start.end():])
        stop=start.end()+end.end() if end else len(text)
        text=text[:start.start()]+'[REDACTED]'+text[stop:];count+=1
    for pattern in PATTERNS:
        text,found=re.subn(pattern,'[REDACTED]',text)
        count+=found
    for name in ('LLM_API_KEY','OPENAI_API_KEY','RUNNER_TOKEN','POSTGRES_PASSWORD'):
        value=os.getenv(name,'')
        if len(value)>=8 and value in text:
            count+=text.count(value);text=text.replace(value,'[REDACTED]')
    return text,count

def excluded(name):
    parts=PurePosixPath(name).parts
    return any(p.startswith('.') or p.lower()=='node_modules' or p.lower().startswith(('oracle','ground-truth','ground_truth')) for p in parts) or PurePosixPath(name).suffix.lower() in ('.pem','.key','.p12')

def sanitize_files(files):
    safe=[]; manifest=[]
    for name,text in files:
        if excluded(name):
            manifest.append({'name':name,'excluded':True,'redactions':0});continue
        content,count=redact(text)
        safe.append((name,content))
        manifest.append({'name':name,'excluded':False,'redactions':count,'characters':len(content)})
    return safe,manifest

def sanitize_value(value):
    if isinstance(value,str):return redact(value)[0]
    if isinstance(value,list):return [sanitize_value(v) for v in value]
    if isinstance(value,dict):return {k:sanitize_value(v) for k,v in value.items()}
    return value
