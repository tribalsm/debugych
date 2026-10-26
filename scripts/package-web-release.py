"""Package committed sources, production dist and selected local QA evidence, never .env or caches."""
from pathlib import Path
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
out = root / 'outputs/web-integration/debugych-web-release.zip'
out.parent.mkdir(parents=True, exist_ok=True)
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
files = {root / name for name in tracked if name and not name.startswith(('outputs/', '.github/'))}
files.update((root / 'apps/web/dist').rglob('*'))
evidence = ['dashboard.png', 'import-workspace.png', 'test-studio.png', 'bug-proof.png', 'diff.png',
            'verified.png', 'demo.mp4', 'free-verify.json', 'ai-before.json', 'ai-after.json',
            'browser-final.log', 'source-links.log', 'baseline-backend.log', 'typecheck.log',
            'lint.log', 'unit-final.log', 'build.log', 'server-smoke.log']
files.update(out.parent / name for name in evidence)
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(files):
        if path.is_file():
            rel = path.relative_to(root)
            if path.name == '.env' or any(p in {'.git', 'node_modules', '__pycache__'} for p in rel.parts):
                raise RuntimeError(f'Forbidden release file: {rel}')
            archive.write(path, 'debugych-web-release/' + rel.as_posix())
with zipfile.ZipFile(out) as archive:
    if archive.testzip():
        raise RuntimeError('Archive integrity check failed')
print(f'{out}\n{out.stat().st_size:,} bytes')
