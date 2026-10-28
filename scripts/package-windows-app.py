"""Package the existing web/backend and GUI host; never include local credentials or database volumes."""
from pathlib import Path
import shutil, subprocess, zipfile, json, hashlib, os

root=Path(__file__).resolve().parents[1]
version=json.loads((root/'apps/desktop/tauri.conf.json').read_text(encoding='utf-8'))['version']
out=root/'outputs/windows-app'
out.mkdir(parents=True,exist_ok=True)
resources=out/'resources'
resources.mkdir(exist_ok=True)
server_default=root/'infra/server/client-default.json'
if server_default.is_file():shutil.copy2(server_default,resources/'server-default.json')
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
# Explicit evidence allowlist: never bundle arbitrary local diagnostics or user profiles.
for name in ['baseline-rust.log', 'baseline-pet.log', 'baseline-web.log', 'baseline-browser.log', 'baseline-bootstrap.log', 'rust-tests.log', 'bridge-tests.log', 'launcher-proxy-linux.log', 'typecheck.log', 'lint.log', 'web-build.log', 'pet-typecheck.log', 'pet-embed.log', 'release-final.log', 'shell-browser-tests.log', 'installed-modes-smoke.log', 'installed-modes-smoke.json', 'installed-modes-first-attempt.log', 'running-update-guard.json', 'installation-check.json', 'update-check.json', 'uninstall-check.json', 'reinstall-check.json', 'shortcut-launch-check.json', 'portable-owned-after.json', 'legacy-conflict-processes.json', 'legacy-blocked-children.json', 'installed-test-cleanup.json', 'native-diagnostics.png', 'native-legacy-conflict.png', 'installer-finished.png', 'saved-qa-api-smoke.json', 'provider-config.json', 'ai-before.json', 'ai-after.json', 'dependencies.json', 'shared-services-check.json', 'listeners.json', 'video-metadata.json', 'video-overview-control.png', 'debugych_desktop_1.2_overview.mp4']:
 source=root/'outputs/desktop12'/name
 if source.is_file():shutil.copy2(source,evidence/name)
validation=root/'docs/desktop-account-login.md'
if not validation.is_file():validation=root/'docs/debugych-server-1.0.md'
if not validation.is_file():validation=root/'docs/desktop-1.2-validation.md'
if validation.is_file():shutil.copy2(validation,out/'VALIDATION.md')
for name in ['new-domain-validation.json','live-token-rotation.json','native-remote-connection.json','vps-control-e2e.json','vps-gvisor-workloads.log','owner-auth-tests.log','backend-regression-final.log','proxy-auth-tests.log','rust-auth-tests.log','vps-restore-retry.log']:
 source=root/'outputs/server10'/name
 if source.is_file():shutil.copy2(source,evidence/name)
for name in ['desktop-account-rust.log','desktop-account-live-rust.log','desktop-account-node-tests.log','desktop-account-shell.log','desktop-account-bridge.log','desktop-account-typecheck.log','desktop-account-lint.log','desktop-account-web-build.log','desktop-account-web-unit.log','desktop-account-release-build.log','desktop-account-connection.png']:
 source=root/'outputs/server10'/name
 if source.is_file():shutil.copy2(source,evidence/name)
meta={'version':version,'pet':'embedded v3.2.1 transparent window; same process and connection','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'exeSha256':hashlib.sha256((out/'Debugych.exe').read_bytes()).hexdigest(),'web':'existing production build','engine':'unchanged','runtime':'Tauri 2 + Windows WebView2 + bundled Node','requires':'configured Linux Docker/gVisor for local QA; remote HTTPS mode available','paidCallsDuringPackaging':0}
(out/'build.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
archive=root/f'outputs/debugych_desktop_{version}_windows.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in out.rglob('*'):
  if p.is_file() and p.name not in {"native-runtime.json","native-startup-error.txt"}:
   assert p.name not in {'.env','backend.env','connection.json','companion.json','chat-history.json'}
   z.write(p,'Debugych/'+p.relative_to(out).as_posix())
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(str(out/'Debugych.exe'));print(str(archive));print(archive.stat().st_size)
