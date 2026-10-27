"""Package the existing web/backend and GUI host; never include local credentials or database volumes."""
from pathlib import Path
import shutil, subprocess, zipfile, json, hashlib, os

root=Path(__file__).resolve().parents[1]
out=root/'outputs/windows-app'
out.mkdir(parents=True,exist_ok=True)
resources=out/'resources'
resources.mkdir(exist_ok=True)
target=Path(os.environ.get('CARGO_TARGET_DIR',root/'apps/desktop/target'))
def copy_binary(source,destination):
 if not destination.exists() or hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(destination.read_bytes()).digest():
  shutil.copy2(source,destination)
copy_binary(target/'release/debugych-desktop.exe',out/'Debugych.exe')
node=Path(shutil.which('node')).resolve()
(resources/'runtime').mkdir(exist_ok=True)
copy_binary(node,resources/'runtime/node.exe')
shutil.copy2(node.parent/'LICENSE',resources/'runtime/NODE-LICENSE.txt')
(resources/'scripts').mkdir(exist_ok=True)
shutil.copy2(root/'scripts/serve-web.mjs',resources/'scripts/serve-web.mjs')
shutil.copy2(root/'scripts/ensure-backend.ps1',resources/'ensure-backend.ps1')
shutil.copytree(root/'apps/web/dist',resources/'apps/web/dist',dirs_exist_ok=True)
backend=resources/'backend'
for directory in ['apps/api','services','demo','infra']:
 shutil.copytree(root/directory,backend/directory,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','node_modules','target'))
for name in ['requirements.txt','docker-compose.yml','alembic.ini','.env.example','.dockerignore']:
 shutil.copy2(root/name,backend/name)
docs=root/'docs/windows-desktop.md'
if docs.exists():shutil.copy2(docs,out/'README.md')
evidence=out/'evidence';evidence.mkdir(exist_ok=True)
for name in ['windows-desktop-dashboard.png','windows-desktop-settings.png','windows-desktop-offline.png','desktop-validation.json','desktop-rust-tests.log','desktop-bootstrap-tests.log','desktop-proxy-regression.log','desktop-static-regression.log','desktop-browser-tests.log']:
 source=root/'outputs/web-integration'/name
 if source.exists():shutil.copy2(source,evidence/name)
meta={'version':'1.0.0','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'exeSha256':hashlib.sha256((out/'Debugych.exe').read_bytes()).hexdigest(),'web':'existing production build','engine':'unchanged','runtime':'Tauri 2 + Windows WebView2 + bundled Node','requires':'configured Linux Docker/gVisor for local QA; remote HTTPS mode available','paidCallsDuringPackaging':0}
(out/'build.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
archive=root/'outputs/debugych_windows_app.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in out.rglob('*'):
  if p.is_file():
   assert p.name not in {'.env','backend.env','connection.json','companion.json','chat-history.json'}
   z.write(p,'Debugych/'+p.relative_to(out).as_posix())
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(str(out/'Debugych.exe'));print(str(archive));print(archive.stat().st_size)
