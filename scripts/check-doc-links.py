"""Check local Markdown targets only; no external HTTP requests or content execution."""
import re
import sys
from pathlib import Path
from urllib.parse import unquote,urlsplit

paths=[]
for argument in sys.argv[1:]:
    item=Path(argument)
    paths.extend(item.rglob('*.md') if item.is_dir() else [item])
missing=[]
for path in paths:
    if not path.is_file():missing.append((str(path),'document missing'));continue
    for target in re.findall(r'\]\(([^\s)]+)\)',path.read_text(encoding='utf-8')):
        parsed=urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith(('#','/')):continue
        if parsed.path and not (path.parent/unquote(parsed.path)).exists():missing.append((str(path),target))
for path,target in missing:print(path+' -> '+target)
print(f'Checked {len(paths)} Markdown documents; missing targets: {len(missing)}')
raise SystemExit(bool(missing))
