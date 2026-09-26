"""Defense headers + CORS — fail-closed, environment-driven.

- Security headers on every response (HSTS only in production to avoid
  bricking local http dev). No inline-script exceptions needed (no CSP yet —
  Next.js inline runtime chunks would break; CSP lands with a nonce plan).
- CORS: exact allowlist from APP_URL (+ localhost dev). Credentials enabled
  only for listed origins; everything else gets no ACAO header.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware


def apply_security_headers(response, *, is_prod: bool = False):  # type: ignore[no-untyped-def]
    """Attach defense headers to any response (including error/preflight)."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if is_prod:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        from .config import get_settings

        from fastapi.responses import Response as _Plain

        is_prod = get_settings().is_prod
        origin = request.headers.get("origin", "")
        allowed = origin in _allowed_origins()
        if request.method == "OPTIONS" and allowed:
            # CORS preflight short-circuit (no auth needed to ask permission).
            resp = _Plain(status_code=204, headers={
                "Access-Control-Allow-Origin": origin, "Vary": "Origin",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Request-ID, Idempotency-Key",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Max-Age": "600"})
            return apply_security_headers(resp, is_prod=is_prod)
        response = await call_next(request)
        apply_security_headers(response, is_prod=is_prod)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            vary = response.headers.get("Vary")
            response.headers["Vary"] = f"{vary}, Origin" if vary else "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Request-ID, Idempotency-Key"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response


def _allowed_origins() -> set[str]:
    from .config import get_settings

    s = get_settings()
    origins = {s.app_url.rstrip("/")}
    if not s.is_prod:
        origins |= {"http://localhost:3000", "http://127.0.0.1:3000"}
    return origins
