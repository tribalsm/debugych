"""Real PostgreSQL cosine search with local multilingual embeddings; no LLM."""
import json
import os
import urllib.request
from uuid import uuid4

BASE=os.getenv('API_BASE','http://127.0.0.1:8000').rstrip('/')
if BASE!='http://127.0.0.1:8000':raise SystemExit('This smoke test targets its own local Compose API only')
client=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path,body=None,method=None):
    payload=None if body is None else json.dumps(body).encode()
    with client.open(urllib.request.Request(BASE+path,data=payload,method=method,headers={'Content-Type':'application/json'}),timeout=90) as reply:return json.load(reply)

def upload(pid,name,content):
    boundary=uuid4().hex;body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/plain\r\n\r\n{content}\r\n--{boundary}--\r\n').encode()
    with client.open(urllib.request.Request(BASE+f'/api/projects/{pid}/files',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=20) as reply:assert reply.status==201

def main():
    ids=[]
    try:
        for name in ('Retrieval public control','Separate private control'):
            ids.append(request('/api/projects',{'name':name})['id'])
        upload(ids[0],'requirements.md','A payment must be accepted when the account balance exactly equals the purchase amount.')
        upload(ids[0],'garden.md','Water basil and tomatoes every morning. Flowers need fertile soil.')
        upload(ids[1],'private.md','Private payment rules belonging to a different project.')
        query={'query':'Оплата при равенстве остатка на счёте и суммы покупки','limit':1}
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            result,private=list(pool.map(lambda pid:request(f'/api/projects/{pid}/context-search',query),ids))
        assert private['mode']=='pgvector-semantic'
        assert result['mode']=='pgvector-semantic',result['mode']
        assert result['matches'][0]['path']=='requirements.md',result['matches']
        assert all('Private payment' not in m['content'] for m in result['matches'])
        reused=request(f'/api/projects/{ids[0]}/context-search',query);assert reused['reused'] and reused['version']==result['version']
        upload(ids[0],'new.md','Refunds restore the balance.')
        refreshed=request(f'/api/projects/{ids[0]}/context-search',query);assert refreshed['version']!=result['version']
        assert request(f'/api/projects/{ids[0]}/ai-statistics')['attempts']==0
        print(json.dumps({'mode':result['mode'],'encoder':result['encoder'],'cross_language_top1':result['matches'][0]['path'],'project_isolation':True,'reused':True,'refreshed':True,'llm_requests':0}))
    finally:
        for pid in ids:request('/api/projects/'+pid,method='DELETE')

if __name__=='__main__':main()
