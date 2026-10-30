"""Standalone, stdlib-only remote CI client. Never executes repository code locally."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID
import zipfile

EXCLUDED = {'node_modules', 'vendor', 'dist', 'build', 'coverage', 'artifacts', 'outputs', 'debugych-report', 'debugych_ci', '__pycache__', 'venv', 'env'}
SUFFIXES = {'.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.html', '.css', '.json', '.java', '.md'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def source_files(root):
    result = {}
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in EXCLUDED and not (Path(folder) / d).is_symlink())
        for name in sorted(names):
            path = Path(folder) / name
            if path.is_symlink() or name.startswith('.') or path.suffix.lower() not in SUFFIXES: continue
            if re.search(r'(secret|credential|token|password|private.?key|service.?account|^env\.)', name, re.I): continue
            relative = path.relative_to(root).as_posix()
            if len(relative) > 200 or ':' in relative or '\\' in relative: raise ValueError('Unsupported source path')
            data = path.read_bytes()
            if not data: continue
            if len(data) > 1024 * 1024: raise ValueError('Source file exceeds 1 MB limit')
            data.decode('utf-8-sig')
            result[relative] = data
            if len(result) > 60 or sum(map(len, result.values())) > 1500000:
                raise ValueError('Source exceeds CI snapshot limits (60 files / 1.5 MB)')
    return result


def package(root, plan_path):
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if plan.get('version') != 1 or plan.get('framework') not in ('pytest', 'playwright'):
        raise ValueError('Unsupported CI manifest')
    entries = plan.get('tests')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 40: raise ValueError('Invalid test manifest')
    files = source_files(root); selected = []
    for entry in entries:
        name = entry['path']
        pattern = r'debugych_ci/tests/test_[0-9a-f-]{36}\.py' if plan['framework'] == 'pytest' else r'debugych_ci/tests/[0-9a-f-]{36}\.spec\.ts'
        if not re.fullmatch(pattern, name) or name in selected: raise ValueError('Invalid test path')
        path = root / name
        if any(p.is_symlink() for p in (path, path.parent, path.parent.parent)): raise ValueError('Test symlink forbidden')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']: raise ValueError('Exported test hash changed; export a new CI package')
        if not data or len(data.decode('utf-8')) > 16000: raise ValueError('Invalid test module')
        files[name] = data; selected.append(name)
    if sum(map(len, files.values())) > 1900000: raise ValueError('Combined source and tests exceed snapshot limit')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items(): archive.writestr(name, data)
    return buffer.getvalue(), selected, sorted(files)


class Client:
    def __init__(self, base):
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('DEBUGYCH_BASE_URL must be an HTTPS origin')
        self.base = base.rstrip('/'); self.cookie = ''
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, data=None, content_type='application/json'):
        headers = {'Origin': self.base, 'Content-Type': content_type}
        if self.cookie: headers['Cookie'] = self.cookie
        if isinstance(data, dict): data = json.dumps(data).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                body = response.read(16000001)
                if len(body) > 16000000: raise ValueError('Server response exceeds limit')
                return body
        except urllib.error.HTTPError as error:
            # Never print server body or credentials, including redirects.
            raise RuntimeError(f'Debugych request failed: HTTP {error.code}') from None

    def login(self, username, password):
        body = urllib.parse.urlencode({'username': username, 'password': password}).encode()
        request = urllib.request.Request(self.base + '/auth/sign-in', data=body, headers={'Origin': self.base, 'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            self.opener.open(request, timeout=30).close()
        except urllib.error.HTTPError as response:
            if response.code != 303 or response.headers.get('Location') != '/auth/account': raise RuntimeError('Account login failed') from None
            for cookie in response.headers.get_all('Set-Cookie', []):
                match = re.match(r'(__Host-debugych=[0-9a-f]{64});', cookie)
                if match and '; secure' in cookie.lower() and '; httponly' in cookie.lower() and 'domain=' not in cookie.lower():
                    self.cookie = match.group(1)
        if not self.cookie: raise RuntimeError('Account session was not established')

    def json(self, method, path, data=None):
        return json.loads(self.request(method, path, data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, default=Path('debugych-report'))
    parser.add_argument('--list-files', action='store_true')
    args = parser.parse_args(); root = args.root.resolve()
    archive, paths, names = package(root, root / 'debugych_ci/plan.json')
    if args.list_files:
        print('\n'.join(names)); return 0
    client = Client(os.environ.get('DEBUGYCH_BASE_URL', ''))
    username = os.environ.get('DEBUGYCH_USERNAME', ''); password = os.environ.get('DEBUGYCH_PASSWORD', '')
    if not username or not password: raise ValueError('Set dedicated account credentials in CI secrets')
    client.login(username, password)
    pid = None
    try:
        project = client.json('POST', '/api/projects', {'name': 'CI ' + time.strftime('%Y%m%d-%H%M%S', time.gmtime())})
        pid = str(UUID(project['id'])); print('Temporary CI project: ' + pid)
        print('Uploading source and frozen tests')
        boundary = 'debugych-ci-' + os.urandom(12).hex()
        payload = ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="source.zip"\r\nContent-Type: application/zip\r\n\r\n').encode() + archive + ('\r\n--' + boundary + '--\r\n').encode()
        client.request('POST', f'/api/projects/{pid}/files', payload, 'multipart/form-data; boundary=' + boundary)
        client.json('POST', f'/api/projects/{pid}/import-tests', {'paths': paths})
        print('Starting gVisor execution')
        run = client.json('POST', f'/api/projects/{pid}/runs', {})
        rid = str(UUID(run['id'])); deadline = time.monotonic() + 300
        while run.get('status') not in ('completed', 'failed', 'manual_review_required', 'cancelled'):
            if time.monotonic() > deadline: raise RuntimeError('CI execution timed out; project may still be running')
            time.sleep(2)
            run = client.json('GET', f'/api/runs/{rid}')
        args.output.mkdir(parents=True, exist_ok=True)
        print('Downloading JUnit report')
        xml = client.request('GET', f'/api/exports?project_id={pid}&format=junit&run_id={rid}')
        (args.output / 'junit.xml').write_bytes(xml)
        import xml.etree.ElementTree as ET
        report = ET.fromstring(xml)
        summary = {key: int(report.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
        summary.update({'run_id': rid, 'status': run.get('status'), 'runtime': run.get('runtime')})
        (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary))
        return 0 if run.get('status') == 'completed' and run.get('runtime') == 'runsc' and summary['tests'] > summary['skipped'] and summary['failures'] == summary['errors'] == 0 else 1
    finally:
        if pid:
            try: client.json('DELETE', f'/api/projects/{pid}')
            except Exception: print('Cleanup incomplete: remove temporary CI project ' + pid, file=sys.stderr)


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as error:
        # Do not echo source paths, response bodies, connection strings or credentials.
        print('Debugych CI failed (' + type(error).__name__ + '). Check configuration, account quotas and server availability.', file=sys.stderr)
        if re.fullmatch(r'Debugych request failed: HTTP [0-9]{3}',str(error)):
            print(str(error),file=sys.stderr)
        sys.exit(2)
