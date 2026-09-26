# Test Strategy

Unit:
formulas, normalization, matching, risk scoring, currency/unit logic, regional rules, permissions.

Integration:
upload pipeline, extraction persistence, AI output validation, DB transaction behavior, exports.

E2E:
primary workflow from intake → analysis → human review → report.

Security:
auth bypass, IDOR, cross-tenant access, upload abuse, XSS, SSRF, prompt injection, secret leakage.

AI eval:
golden extraction accuracy, schema compliance, evidence correctness, non-fabrication and refusal behavior.

Test IDs:
DOMAIN-FUNCTION-CASE.

Minimum:
critical domain services >90% target; permission tests for all material endpoints; all critical formulas covered; primary E2E happy path; negative test for every acceptance-critical rule.
