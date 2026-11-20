# Security

## Reporting a vulnerability

Open a private security advisory on the GitHub repository (Security → Report a vulnerability) rather than a public issue.

## Threat model in short

| Asset | Main threat | Control |
|---|---|---|
| Spend data (documents, line items) | Cross-user / cross-role reads | Every query is scoped by `get_visible_user_ids()`; buyer↔buyer, finance↔finance, a single admin sees everything. Covered by `tests/test_rbac_audit.py` |
| Privileged actions | Role escalation | Roles checked server-side (`require_role`); self-registration can only pick `buyer`/`finance`; every router is default-deny |
| Accounts | Credential stuffing, brute force | bcrypt hashes, per-IP rate limit on `/auth/*`, per-account lockout (5 failures / 15 min), password min length 10 |
| LLM prompts | Prompt injection from uploaded documents | Agent tools are read-only and user-scoped; input/output guardrails; tool observations and evidence are sanitized |
| Uploads | Oversized or disguised files | Bounded read, extension allowlist, magic-byte check |
| Frontend | XSS leading to token theft | No raw HTML rendering anywhere; CSP `script-src 'self'` |
| Secrets / config | Insecure defaults in production | Startup refuses default `SECRET_KEY`, `DATABASE_URL`, localhost-only `CORS_ORIGINS` |

Response headers: the API sends `nosniff`, `X-Frame-Options: DENY`, a restrictive CSP (except the Swagger pages) and HSTS in production. The frontend sets the equivalent headers in `frontend/vercel.json`.

## Known limitations (deliberate, documented)

- **JWT in `localStorage`, 60-minute lifetime, no revocation or refresh.** Moving to an httpOnly cookie means `SameSite=None; Secure` plus CSRF protection across the Vercel/Render origins, a real architecture change. The risk is contained by the no-raw-HTML rule and the CSP.
- **Rate limiting and login lockout are in memory.** Fine for the single-instance deployment; with more than one instance they need a shared store (Redis). The container trusts `X-Forwarded-For` from the platform proxy (`--forwarded-allow-ips="*"`), so it must only be reachable through that proxy.
- **Uploads are stored on local disk**, which is ephemeral on Render's free tier, and are not scanned for malware.
- **The public demo accepts open registration.** Everything uploaded is visible to accounts of the same role. Do not upload real data. The demo admin account's password is not published; the seed script takes it from `DEMO_ADMIN_PASSWORD` or generates one.
- **Uploaded-document prompt injection** is only harmless while agent tools stay read-only. Adding a write-capable tool means re-opening this threat model.

## Dependency hygiene

CI runs `pip-audit` (non-blocking) and `npm audit --audit-level=high` (blocking); Dependabot is enabled.
