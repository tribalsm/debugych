"""Provision/rotate owner credentials to private files, never to stdout."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets

def provision(hashes, client_out, api_uid=None):
    hashes, client_out = Path(hashes), Path(client_out)
    if hashes.resolve() == client_out.resolve():
        raise ValueError('Use separate server hash and client token files')
    token = secrets.token_urlsafe(48)
    # The raw token is delivered to the owner out of band, not mounted into API.
    for path, value in [(client_out, token), (hashes, hashlib.sha256(token.encode()).hexdigest())]:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.new')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='ascii') as output:
                output.write(value + '\n')
                output.flush()
                os.fsync(output.fileno())
            if path == hashes and api_uid is not None:
                os.chown(temporary, api_uid, api_uid)
                os.chmod(temporary, 0o400)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hashes', required=True)
    parser.add_argument('--client-out', required=True)
    parser.add_argument('--api-uid', type=int)
    args = parser.parse_args()
    provision(args.hashes, args.client_out, args.api_uid)
    print('Credential files written. Previous token revoked. Transfer the client file securely; do not log it.')
