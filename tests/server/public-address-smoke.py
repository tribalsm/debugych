"""Public read-only HTTPS availability from an independent runner. No credentials."""
import json
from pathlib import Path
import ssl
import urllib.request

BASE='https://debugych.89-22-232-119.sslip.io:9443'

def main():
    checks=[]
    for route,content_type in [('/','text/html'),('/auth/login','text/html'),('/api/health','application/json')]:
        request=urllib.request.Request(BASE+route,headers={'User-Agent':'Debugych-public-access-check/1.0'})
        with urllib.request.urlopen(request,timeout=25,context=ssl.create_default_context()) as reply:
            assert reply.status==200 and reply.headers.get_content_type()==content_type
            assert reply.url.startswith(BASE+'/')
            if route=='/api/health':assert isinstance(json.load(reply),dict)
            checks.append({'route':route,'status':reply.status,'content_type':content_type,'tls_verified':True})
    output=Path('outputs/server10/rag-ts/public-access.json');output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps({'scope':'public read-only access, not live sandbox health','checks':checks},indent=2))
    print(json.dumps(checks))

if __name__=='__main__':main()
