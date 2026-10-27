"""Export tracked source, excluding local data, historical outputs and build products."""
from pathlib import Path
import subprocess, zipfile, json

root = Path(__file__).resolve().parents[1]
out = root / 'outputs/debugych_desktop_1.2_sources.zip'
names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
excluded = {'outputs', 'node_modules', 'target', '.git', '__pycache__', 'dist'}
private = {'.env', 'backend.env', 'connection.json', 'chat-history.json', 'companion.json'}
count = 0
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name in names:
        path = Path(name)
        if not name or set(path.parts) & excluded or path.name in private:
            continue
        if (root / path).is_file():
            archive.write(root / path, 'Debugych-source/' + path.as_posix())
            count += 1
    archive.writestr('Debugych-source/source-build.json', json.dumps({
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip(),
        'files': count, 'build': 'scripts/build-windows-app.ps1',
        'notes': 'Install locked npm dependencies before building. No credentials, database or local user history.'
    }, indent=2))
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
print(out)
