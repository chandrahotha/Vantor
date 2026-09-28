<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Browser Security

Add CSP, secure cookies where used, strict CORS, frame policy, Trusted Types where feasible, DOM-safe rendering, no secret persistence in localStorage, and rigorous output encoding. Keep BYOK secrets out of browser persistence and logs.

## Now implemented (2026-09-28)

CSP, frame policy, strict CORS and the security headers are enforced on **both** hosts, and the
reason is the substantive part: a Content-Security-Policy delivered by the API governs documents
the *API* serves. The pages a user actually reads are served by Next, from a different origin,
so the policy meant to protect the application UI was nowhere near it and the app ran with no
CSP at all. `frontend/next.config.mjs` now carries a policy on the app's own responses:
`default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`,
`frame-ancestors 'none'`, plus `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a
restrictive `Permissions-Policy`. Allowed origins are derived from `NEXT_PUBLIC_API_URL` and
`NEXT_PUBLIC_KEYCLOAK_URL` rather than hardcoded, and `frontend/next.config.test.ts` asserts
it.

Honest limitations:

- The app's `script-src` requires `'unsafe-inline'` because Next injects its own bootstrap
  script. A nonce cannot reach a build-time asset, so this one directive is weaker than the
  API's, and it is labelled in the config rather than quietly widened.
- **`strict-dynamic` is deliberately absent.** Next's bootstrap script arrives without a nonce,
  so adding the directive would make the app depend on a nonce it does not control.
- HSTS and `upgrade-insecure-requests` are emitted only when the app is actually served over
  https, so the configuration never claims a protection it is not providing.
- Trusted Types is not implemented. Output encoding relies on React's default escaping with no
  explicit encoding pass.
- No secret is persisted in `localStorage`; the BYOK key is sent as the
  `X-Vantor-Provider-Key` header and never in a JSON body or a log.
