"""HTTP security headers middleware for the Lexi API.

Phase 15 (production hardening): every response — including errors and
CORS pre-flights — carries conservative security headers. These headers
cost nothing at runtime and harden the API against clickjacking, MIME
sniffing, referrer leakage, and cross-origin isolation attacks when the
API is opened directly in a browser.

CSP is intentionally minimal for a JSON API (no HTML is served, so
``default-src 'none'`` with ``frame-ancestors 'none'`` is safe and strict).
X-Frame-Options is added for legacy clients that ignore CSP.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# HSTS is safe on Render: TLS terminates at Render's edge, and browsers
# only apply the header over HTTPS (ignored on local http://localhost).
_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach conservative security headers to every response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _HEADERS.items():
            response.headers.setdefault(header, value)
        return response


def add_security_headers(app: Any) -> None:
    """Register the security headers middleware on a FastAPI application."""
    app.add_middleware(SecurityHeadersMiddleware)
