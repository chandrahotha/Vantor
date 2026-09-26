# Security Manual

Threats:
malicious PDF/XLSX/DOCX/ZIP, prompt injection, OCR poisoning, oversized files, malformed spreadsheets, XSS, SQL injection, SSRF, IDOR, tenant breakout, secret leakage, AI tool abuse, webhook spoofing/replay, DoS, malicious exports.

Mandatory:
- OIDC/OAuth2 and MFA where supported
- deny-by-default RBAC and object-level authorization
- MIME + extension + magic-byte checks
- upload size/decompression limits
- quarantine + malware scan
- never execute macros/scripts
- immutable file versions
- CSP/HSTS/secure cookies
- parameterized SQL
- least-privilege DB/service accounts
- secret manager + CI secret scanning
- schema validation for all AI output
- allowlisted AI tools only
- no arbitrary shell/SQL/HTTP tools
- server-side export authorization
- audit material actions
- rate limiting/WAF
- safe error messages

Manual pre-release:
[ ] secrets absent from current tree/history
[ ] no production data in demo seed
[ ] IDOR tested
[ ] cross-tenant test
[ ] malicious upload tests
[ ] prompt injection tests
[ ] XSS/SSRF tests
[ ] rate limits
[ ] audit coverage
[ ] error leakage check
