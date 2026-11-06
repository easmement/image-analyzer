"""Reject requests that didn't come from a localhost page: a defence against DNS rebinding.

Binding to 127.0.0.1 keeps other machines out, but not other websites: a page on evil.example
can re-point its own domain at 127.0.0.1 and then call this API from your browser, as if it were
same-origin. Its requests still carry the attacker's name, though: in Host when calling the
backend directly, and in X-Forwarded-Host and Origin when going through the Next.js proxy (which
rewrites Host to 127.0.0.1:8001 but passes those two through). So every one of them present must
name localhost.
"""

import json
from urllib.parse import urlsplit

from image_analyzer.core.config import settings

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"} | ({settings.host} - {"0.0.0.0", "::"})


def _hostname(value: str) -> str:
    """'localhost:3000' -> 'localhost', '[::1]:8001' -> '::1', 'http://localhost:3000' -> 'localhost'."""
    netloc = urlsplit(value).netloc if "://" in value else value
    return (urlsplit(f"//{netloc}").hostname or "").lower()


class LocalhostOnlyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        checks = [headers.get("host", ""), headers.get("x-forwarded-host", "")]
        if (origin := headers.get("origin")) and origin != "null":
            checks.append(origin)
        for value in filter(None, (c.split(",")[0].strip() for c in checks)):
            if _hostname(value) not in ALLOWED_HOSTS:
                body = json.dumps({"detail": f"Requests must come from localhost, not {_hostname(value)!r}"}).encode()
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        return await self.app(scope, receive, send)
