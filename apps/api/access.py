"""Single-owner, fail-closed ASGI gate. No token values in logs or responses."""
import hashlib
import hmac
import os
from pathlib import Path
from starlette.responses import JSONResponse

class OwnerAccess:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        required = os.getenv('DEBUGYCH_AUTH_MODE', 'off') == 'required'
        production = os.getenv('DEBUGYCH_SERVER', '0') == '1'
        # Only an infrastructure liveness response is anonymous. No API/config data.
        if scope['type'] == 'http' and scope.get('path') == '/healthz' and scope['method'] in ('GET', 'HEAD'):
            return await JSONResponse({'status': 'alive'})(scope, receive, send)
        status = None
        if production and not required:
            status = 503
        elif required:
            try:
                path = Path(os.environ['DEBUGYCH_AUTH_HASHES_FILE'])
                if path.stat().st_size > 4096:
                    raise ValueError('Oversized credential configuration')
                hashes = path.read_text(encoding='ascii').splitlines()
                if not 1 <= len(hashes) <= 8 or any(len(x) != 64 or any(c not in '0123456789abcdef' for c in x) for x in hashes):
                    raise ValueError('Invalid credential configuration')
            except (OSError, KeyError, ValueError, UnicodeError):
                status = 503
            else:
                headers = [v for k, v in scope.get('headers', []) if k.lower() == b'authorization']
                value = headers[0] if len(headers) == 1 else b''
                token = value[7:] if value.startswith(b'Bearer ') else b''
                digest = hashlib.sha256(token).hexdigest()
                matched = [hmac.compare_digest(digest, x) for x in hashes]
                if not 43 <= len(token) <= 256 or not all(33 <= c <= 126 for c in token) or not any(matched):
                    status = 401
        if status:
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 4401 if status == 401 else 1013})
            return await JSONResponse({'detail': 'Требуется действующий токен доступа' if status == 401 else 'Серверная авторизация не настроена'}, status_code=status,
                                      headers={'Cache-Control': 'no-store', 'WWW-Authenticate': 'Bearer'})(scope, receive, send)
        if production and scope['type'] == 'http':
            # Proxy also enforces this cap; count chunked bodies without buffering them.
            limit = 40 * 1024 * 1024
            headers = dict(scope.get('headers', []))
            try:
                length = int(headers.get(b'content-length', b'0'))
            except ValueError:
                length = limit + 1
            if length < 0 or length > limit:
                return await JSONResponse({'detail': 'Request body too large'}, status_code=413)(scope, receive, send)
            consumed = 0
            async def bounded_receive():
                nonlocal consumed
                message = await receive()
                consumed += len(message.get('body', b''))
                if consumed > limit:
                    from starlette.exceptions import HTTPException
                    raise HTTPException(413, 'Request body too large')
                return message
            return await self.app(scope, bounded_receive, send)
        return await self.app(scope, receive, send)
