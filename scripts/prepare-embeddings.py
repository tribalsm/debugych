"""Download a pinned, public local embedding model. No API keys or inference API."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

REVISION='2c4055b12046f11709e9df2c122e59ffbdc2f900'
FILES={'tokenizer.json':'b60b6b43406a48bf3638526314f3d232d97058bc93472ff2de930d43686fa441',
       'onnx/model_quantized.onnx':'66fc00f5f29afcaff34092e1bdd20008ca3918265a82fb9695a551e510cc4ebc'}

def prepare(output):
    for name,expected in FILES.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:continue
        temporary=target.with_suffix('.download')
        try:
            with urllib.request.urlopen(f'https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/{REVISION}/{name}',timeout=120) as reply,temporary.open('wb') as stream:
                digest=hashlib.sha256();size=0
                while block:=reply.read(1024*1024):
                    size+=len(block)
                    if size>140000000:raise ValueError('Model download exceeds limit')
                    digest.update(block);stream.write(block)
            if digest.hexdigest()!=expected:raise ValueError('Embedding model checksum mismatch')
            temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
        print('Verified embedding asset: '+name)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output)
