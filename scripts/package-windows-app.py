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
# Windows PowerShell 5.1 otherwise reads Cyrillic shortcut names as ANSI.
(out/'Create-DesktopShortcut.ps1').write_text((root/'scripts/Create-DesktopShortcut.ps1').read_text(encoding='utf-8'),encoding='utf-8-sig')
evidence=out/'evidence';evidence.mkdir(exist_ok=True)
for name in ['windows-desktop-dashboard.png','windows-desktop-settings.png','windows-desktop-offline.png','desktop-validation.json','desktop-rust-tests.log','desktop-bootstrap-tests.log','desktop-proxy-regression.log','desktop-static-regression.log','desktop-browser-tests.log']:
 # Older packages used this same output folder; do not label old evidence as 1.1.
 old=evidence/name
 if old.is_file():old.unlink()
for name in ['native-desktop11-final.png','native-verification-runsc.png','native-fix-verify-final.png','rust-tests.log','pet-tests.log','web-tests.log','proxy-tests.log','bootstrap-tests.log','desktop-bridge-tests.log','pet-browser-repro.log','sprite-preservation.json','upstream-sprite-check.json','ai-budget-before.json','ai-budget-after.json','backend-health.json','patch-not-applied.json','video-metadata.json','video-validation.json','native-lifecycle-validation.json']:
 source=root/'outputs/desktop11'/name
 if source.is_file():shutil.copy2(source,evidence/name)
shutil.copy2(root/'docs/desktop-1.1-validation.md',out/'VALIDATION.md')
video=root/'outputs/desktop11/debugych_desktop_1.1_demo.mp4'
if video.is_file():shutil.copy2(video,out/video.name)
meta={'version':'1.1.0','pet':'embedded v3.2.1 transparent window; same process and connection','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'exeSha256':hashlib.sha256((out/'Debugych.exe').read_bytes()).hexdigest(),'web':'existing production build','engine':'unchanged','runtime':'Tauri 2 + Windows WebView2 + bundled Node','requires':'configured Linux Docker/gVisor for local QA; remote HTTPS mode available','paidCallsDuringPackaging':0}
(out/'build.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
archive=root/'outputs/debugych_desktop_1.1_windows.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in out.rglob('*'):
  if p.is_file() and p.name not in {"native-runtime.json","native-startup-error.txt"}:
   assert p.name not in {'.env','backend.env','connection.json','companion.json','chat-history.json'}
   z.write(p,'Debugych/'+p.relative_to(out).as_posix())
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(str(out/'Debugych.exe'));print(str(archive));print(archive.stat().st_size)
