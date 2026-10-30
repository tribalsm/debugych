"""Trusted local indexing and project-filtered retrieval. No remote inference."""
import hashlib
import json
from sqlalchemy import select,delete,text
from apps.api.db import ContextChunk,Project
from services.ai.retrieval import chunks,encode,words,MODEL_ID,FALLBACK_ID


def index(db,pid,files):
    # Serialize refreshes with uploads/deletion on PostgreSQL; never trust a caller's version.
    if db.scalar(select(Project).where(Project.id==pid).with_for_update()) is None:raise ValueError('Project not found')
    parts=chunks(files)
    if len(parts)>160:raise ValueError('Index limit: 160 chunks; split the project')
    encoder,_=encode(['context index'])
    version=hashlib.sha256(json.dumps([encoder,parts],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    existing=db.scalars(select(ContextChunk).where(ContextChunk.project_id==pid)).all()
    if len(existing)==len(parts) and all(r.version==version for r in existing):
        return {'version':version,'encoder':encoder,'chunks':len(parts),'reused':True}
    actual,vectors=encode([p['path']+'\n'+p['content'] for p in parts])
    if actual!=encoder:
        encoder=actual;version=hashlib.sha256(json.dumps([encoder,parts],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    db.execute(delete(ContextChunk).where(ContextChunk.project_id==pid))
    db.add_all([ContextChunk(project_id=pid,version=version,encoder=encoder,**part,embedding=json.dumps(vector)) for part,vector in zip(parts,vectors)])
    db.commit()
    return {'version':version,'encoder':encoder,'chunks':len(parts),'reused':False}


def search(db,pid,query,metadata,limit=6,source_only=False):
    encoder,vectors=encode([query]);version=metadata['version']
    if encoder==MODEL_ID and encoder==metadata['encoder'] and db.bind.dialect.name=='postgresql':
        filters=" AND lower(path) NOT LIKE '%.md' AND lower(path) NOT LIKE '%.pdf' AND lower(path) NOT LIKE '%.docx'" if source_only else ''
        rows=db.execute(text('SELECT path,start_line,end_line,content,1-(embedding <=> CAST(:embedding AS vector)) AS score FROM context_chunks WHERE project_id=:pid AND version=:version AND encoder=:encoder'+filters+' ORDER BY embedding <=> CAST(:embedding AS vector),path,start_line,id LIMIT :limit'),
            {'pid':pid,'version':version,'encoder':encoder,'embedding':json.dumps(vectors[0]),'limit':limit}).mappings().all()
        return {'mode':'pgvector-semantic','matches':[dict(r) for r in rows if r['score']>0.05],**metadata}
    rows=db.scalars(select(ContextChunk).where(ContextChunk.project_id==pid,ContextChunk.version==version)).all()
    wanted=set(words(query));ranked=[]
    for row in rows:
        if source_only and row.path.lower().endswith(('.md','.pdf','.docx')):continue
        if encoder==MODEL_ID and row.encoder==MODEL_ID:
            score=sum(a*b for a,b in zip(vectors[0],json.loads(row.embedding)));mode='local-semantic'
        else:
            tokens=set(words(row.path+' '+row.content));score=len(tokens&wanted)/max(1,len(wanted));mode='lexical-fallback'
        if score>0.05:ranked.append({'path':row.path,'start_line':row.start_line,'end_line':row.end_line,'content':row.content,'score':round(score,6)})
    ranked.sort(key=lambda r:(-r['score'],r['path'],r['start_line'],r['content']))
    return {'mode':'local-semantic' if encoder==MODEL_ID and metadata['encoder']==MODEL_ID else 'lexical-fallback','matches':ranked[:limit],**metadata}


def generation_context(db,pid,files,requirements):
    from services.ai.validation import ManualReview
    try:metadata=index(db,pid,files)
    except ValueError as error:raise ManualReview('context_retrieval_insufficient') from error
    documents={name for name,_ in files if name.lower().endswith(('.md','.pdf','.docx'))}
    source=[{'path':name,'content':content} for name,content in files if name not in documents]
    selected={};modes=set()
    for requirement in requirements:
        found=search(db,pid,requirement.text,metadata,limit=2,source_only=True);modes.add(found['mode'])
        for match in found['matches']:selected[(match['path'],match['start_line'],match['content'])]=match
    citations=[{k:r[k] for k in ('path','start_line','end_line','score')} for r in selected.values()]
    if len(json.dumps(source,ensure_ascii=False))<=12000:
        return source,{**metadata,'mode':','.join(sorted(modes)),'selection':'full-source','citations':citations,'requirements_preserved':True}
    # Include a representative match for every explicit requirement or stop for review.
    chosen={}
    for requirement in requirements:
        found=search(db,pid,requirement.text,metadata,limit=1,source_only=True)
        if not found['matches']:raise ManualReview('context_retrieval_insufficient')
        r=found['matches'][0];chosen[(r['path'],r['start_line'],r['content'])]=r
    fragments=[{'path':r['path'],'content':r['content'],'start_line':r['start_line'],'end_line':r['end_line'],'partial':True} for r in chosen.values()]
    if len(json.dumps(fragments,ensure_ascii=False))>12000:raise ManualReview('context_retrieval_insufficient')
    return fragments,{**metadata,'mode':','.join(sorted(modes)),'selection':'retrieved-fragments','citations':[{k:r[k] for k in ('path','start_line','end_line','score')} for r in chosen.values()],'requirements_preserved':True,'source_complete':False}
