"""Local multilingual embeddings, bounded chunks and explicit lexical fallback."""
from functools import lru_cache
import hashlib
import math
import os
from pathlib import Path
import re
import threading

DIMENSIONS=384
MODEL_ID='minilm-multilingual-q8-2c4055b1-v1'
FALLBACK_ID='lexical-hash-v1'
ASSETS={'tokenizer.json':'b60b6b43406a48bf3638526314f3d232d97058bc93472ff2de930d43686fa441',
        'onnx/model_quantized.onnx':'66fc00f5f29afcaff34092e1bdd20008ca3918265a82fb9695a551e510cc4ebc'}
_lock=threading.Lock()

def words(text):
    return re.findall(r'[^\W_]{2,}',re.sub(r'([a-z])([A-Z])',r'\1 \2',text).lower())[:10000]

def lexical(text):
    values=[0.0]*DIMENSIONS
    for word in words(text):
        digest=hashlib.sha256(word.encode()).digest();values[int.from_bytes(digest[:4],'big')%DIMENSIONS]+=1 if digest[4]&1 else -1
    norm=math.sqrt(sum(v*v for v in values)) or 1
    return [round(v/norm,8) for v in values]

@lru_cache(maxsize=2)
def model(directory):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    path=Path(directory)
    for name,digest in ASSETS.items():
        if hashlib.sha256((path/name).read_bytes()).hexdigest()!=digest:raise ValueError('Embedding assets failed verification')
    tokenizer=Tokenizer.from_file(str(path/'tokenizer.json'));tokenizer.enable_truncation(max_length=256);tokenizer.enable_padding()
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.enable_cpu_mem_arena=False;options.enable_mem_pattern=False
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session=ort.InferenceSession(str(path/'onnx/model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    return tokenizer,session

def encode(texts):
    directory=os.getenv('RAG_MODEL_DIR','')
    if os.getenv('RAG_EMBEDDINGS','local')=='lexical' or not directory:
        return FALLBACK_ID,[lexical(t) for t in texts]
    try:
        import numpy as np
        vectors=[]
        with _lock:
            # lru_cache alone allows concurrent cache misses to load two models.
            tokenizer,session=model(directory)
            for start in range(0,len(texts),2):
                batch=tokenizer.encode_batch(texts[start:start+2]);mask=np.array([t.attention_mask for t in batch],dtype=np.int64)
                inputs={'input_ids':np.array([t.ids for t in batch],dtype=np.int64),'attention_mask':mask,'token_type_ids':np.array([t.type_ids for t in batch],dtype=np.int64)}
                hidden=session.run(None,{i.name:inputs[i.name] for i in session.get_inputs()})[0]
                pooled=(hidden*mask[...,None]).sum(axis=1)/np.maximum(mask.sum(axis=1,keepdims=True),1)
                pooled=pooled/np.maximum(np.linalg.norm(pooled,axis=1,keepdims=True),1e-12)
                if pooled.shape!=(len(batch),DIMENSIONS) or not np.isfinite(pooled).all():raise ValueError('Invalid embedding output')
                vectors.extend(pooled.tolist())
        return MODEL_ID,vectors
    except Exception:
        # Never send text to a remote embedding provider as a fallback.
        return FALLBACK_ID,[lexical(t) for t in texts]

def chunks(files):
    from services.ai.privacy import sanitize_files
    safe,_=sanitize_files(files);result=[];total=0
    for name,text in sorted(safe):
        total+=len(text)
        if total>2000000:raise ValueError('Index exceeds 2 million characters')
        lines=text.splitlines(keepends=True);buffer='';start=1;end=1
        for number,line in enumerate(lines,1):
            for offset in range(0,len(line),900):
                piece=line[offset:offset+900]
                if buffer and len(buffer)+len(piece)>900:
                    result.append({'path':name,'start_line':start,'end_line':end,'content':buffer});buffer=''
                if not buffer:start=number
                buffer+=piece;end=number
        if buffer:result.append({'path':name,'start_line':start,'end_line':end,'content':buffer})
        if len(result)>3000:raise ValueError('Index exceeds 3000 chunks')
    return result
