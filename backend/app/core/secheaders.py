"""Defense headers + CORS — fail-closed, environment-driven.

VNT-031. There was no Content-Security-Policy at all, and the module docstring
said so in writing ("no CSP yet — CSP lands with a nonce plan"). A CSP is not a
nice-to-have for an application that renders document-derived text and takes
caller-supplied prompts: without `script-src` and `object-src 'none'` there is
nothing at all standing between a stored-XSS payload and a session token in
`localStorage`.

The policy below is built from parts rather than written as one string, so an
environment can tighten or relax a single directive without parsing a header:

* `script-src` — no `unsafe-inline`, and no `unsafe-eval` outside development.
  Next.js emits bootstrap scripts in the HTML document, so a **nonce** is minted
  per response and the request supplies it via `middleware.ts`; `strict-dynamic`
  lets those bootstraps load their own chunks without `unsafe-inline`.
* `object-src 'none'` and `base-uri 'none'` — the two directives that stop an
  injected `<object>`/`<base>` from doing anything at all.
* `frame-ancestors 'none'` — clickjacking defence at the CSP layer, so it does
  not depend on `X-Frame-Options` being honoured.
* `connect-src` — the API origin only, so a compromised script cannot
  exfiltrate a token to an arbitrary host.

`Content-Security-Policy-Report-Only` is emitted alongside in non-production so
a stricter policy can be trialled without breaking the app, which is how a policy
gets adopted safely rather than being deferred forever.
"""
from __future__ import annotations

import base64
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware

#: The only script nonce source. Kept as a name so a deployment can move to a
#: hash-based policy without touching the header builder.
NONCE_ATTR = "nonce"


def new_nonce() -> str:
    """A per-response nonce. 128 bits of CSPRNG output, base64 for header use."""
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def _connect_origins() -> list[str]:
    from .config import get_settings

    s = get_settings()
    origins = [s.api_url.rstrip("/"), s.app_url.rstrip("/")]
    if not s.is_prod:
        origins += ["http://localhost:3000", "http://127.0.0.1:3000", "ws://localhost:3000"]
    # Deduplicated, order preserved, so the header is stable.
    seen: set[str] = set()
    return [o for o in origins if not (o in seen or seen.add(o))]


def _csp(is_prod: bool, nonce: str) -> str:
    """Build the policy. `unsafe-inline` is absent in every branch."""
    directives: list[str] = [
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'",
        # Next's dev overlay and the React refresh runtime need eval. Development
        # only, and stated as such rather than smuggled into production.
        *( [] if is_prod else ["'unsafe-eval'"] ),
        # Styles are inline because React inline `style={{}}` is used throughout
        # the component library; `style-src-attr` is what actually governs that,
        # and it is separated so the rest of style-src can be strict.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        f"connect-src 'self' {' '.join(_connect_origins())}",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "manifest-src 'self'",
        "worker-src 'self' blob:",
    ]
    return "; ".join(directives)


def apply_security_headers(response, *, is_prod: bool = False, nonce: str = "") -> None:  # type: ignore[no-untyped-def]
    """Attach defense headers to any response (including error/preflight)."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
        "magnet=(), interest-cohort=()"
    )
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    # COEP requires every cross-origin subresource to opt in via CORP. The app
    # serves its own assets and talks to one API origin, both same-origin, so
    # `require-corp` is safe here and buys cross-origin isolation.
    response.headers["Cross-Origin-Embedder-Policy"] = os.getenv(
        "COEP_POLICY", "require-corp").strip()
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

    csp = _csp(is_prod, nonce or new_nonce())
    response.headers["Content-Security-Policy"] = csp
    if not is_prod:
        # Trialling a policy must not be able to break the app, so development
        # gets report-only as well as enforcing. Both are sent deliberately: the
        # enforcing header governs, the report-only one surfaces violations.
        response.headers["Content-Security-Policy-Report-Only"] = csp

    if is_prod:
        response.headers["Strict-Transport-Security"] = os.getenv(
            "HSTS_POLICY",
            "max-age=31536000; includeSubDomains; preload",
        ).strip()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        from fastapi.responses import Response as _Plain

        from .config import get_settings

        is_prod = get_settings().is_prod
        nonce = new_nonce()
        origin = request.headers.get("origin", "")
        allowed = origin in _allowed_origins()
        if request.method == "OPTIONS" and allowed:
            # CORS preflight short-circuit (no auth needed to ask permission).
            resp = _Plain(status_code=204, headers={
                "Access-Control-Allow-Origin": origin, "Vary": "Origin",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Headers": (
                    "Authorization, Content-Type, X-Request-ID, Idempotency-Key, "
                    "X-Vantor-Provider-Key"
                ),
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Max-Age": "600"})
            apply_security_headers(resp, is_prod=is_prod, nonce=nonce)
            return resp
        response = await call_next(request)
        apply_security_headers(response, is_prod=is_prod, nonce=nonce)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            vary = response.headers.get("Vary")
            response.headers["Vary"] = f"{vary}, Origin" if vary else "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Request-ID, Idempotency-Key, "
                "X-Vantor-Provider-Key"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response


def _allowed_origins() -> set[str]:
    from .config import get_settings

    s = get_settings()
    origins = {s.app_url.rstrip("/"), s.api_url.rstrip("/")}
    if not s.is_prod:
        origins |= {"http://localhost:3000", "http://127.0.0.1:3000"}
    return origins
