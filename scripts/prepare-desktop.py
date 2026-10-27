from pathlib import Path
import shutil,json,hashlib
r=Path(__file__).resolve().parents[1];s=r/'apps/pet/web';d=r/'apps/desktop/shell/pet'
shutil.copytree(s,d,dirs_exist_ok=True)
# Verify every sprite byte; no regeneration or conversion during integration.
checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in (s/'assets').glob('*.png')}
for n,h in checks.items():assert hashlib.sha256((d/'assets'/n).read_bytes()).hexdigest()==h
out=r/'outputs/desktop11';out.mkdir(parents=True,exist_ok=True);(out/'sprite-preservation.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print('Prepared one native host with',len(checks),'unchanged sprite sheets')
