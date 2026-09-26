# Security & Efficiency Master Plan — Phase 15

Scores before: Security 85 · Efficiency 88. Target: both ≥ 98.

## Implemented (Critical + High)

| # | Issue | Severity | Score impact | Files | Gain | Risk | Fix strategy |
|---|-------|----------|--------------|-------|------|------|--------------|
| 1 | No security headers on backend responses | HIGH | Security +4 | `app/core/middleware.py` (new), `app/main.py` | Clickjacking/MIME-sniffing/referrer hardening on every response | Very low (headers only) | Header middleware with `setdefault` (CORS pre-flights still get headers) |
| 2 | No security headers on frontend | HIGH | Security +2 | `frontend/next.config.mjs` | HSTS (2y preload), frame-deny, nosniff on all routes | Very low | Next `headers()` config — no CSP (would risk UI breakage) |
| 3 | CORS too permissive (`*` methods/headers) | HIGH | Security +2 | `app/main.py` | Explicit method/header allowlist + pre-flight `max_age=600` (also fewer OPTIONS round-trips) | Very low | Enumerate the 6 methods / 5 headers actually used |
| 4 | Service-role key could authenticate API calls if leaked to a client | HIGH | Security +3 | `app/core/security.py` | `verify_token` rejects `role=service_role` credentials outright | Very low | Payload pre-check before Supabase verification |
| 5 | Raw request bodies logged on 422 (questions/PII reach logs) | HIGH | Security +2, Logging | `app/main.py` | Log-forging/PII vector removed; debuggability kept via `body_length` | Very low | Metadata-only logging |
| 6 | Serial signed-URL generation in documents list (N× storage latency) | HIGH | Efficiency +4 | `app/services/document_service.py` | One round-trip instead of N per page (~100–300 ms each) | Low | `asyncio.gather` over per-row tasks |
| 7 | Cached-compare path fetched `extracted_text` + full analysis needlessly | HIGH | Efficiency +2 | `app/api/compare.py`, `app/services/compare_service.py` | Large-column reads removed from cache hits | Low | `_metadata_only` select variant |
| 8 | No zip-bomb guard on DOCX | MEDIUM | Security +1 | `app/api/upload.py` | Entry-count + 200 MB inflation caps | Very low | Validate before parsing |
| 9 | Page-bomb PDFs fully parsed before rejection | MEDIUM | Security +1, Efficiency +1 | `app/api/upload.py` | 413 in ms instead of after OCR start | Very low | Pre-parse page-count check |
| 10 | ANSI/control chars in titles & search (log/terminal injection) | MEDIUM | Security +1 | `app/utils/sanitize.py` (new), `app/api/upload.py`, `app/api/documents.py` | Control-char hygiene on all free-text inputs | Very low | Shared sanitizer |
| 11 | Chat prompts accepted control characters | MEDIUM | Security +1 | `app/schemas/chat_schema.py` | Pydantic validator on both chat request schemas | Very low | `field_validator` |
| 12 | Unbounded chat history fetch | MEDIUM | Efficiency +1, Security (DoS) | `app/repositories/chat_repository.py` | 200-row cap, contract unchanged | Very low | `.limit(200)` |
| 13 | `useAnalysis` did two serial GETs | MEDIUM | Efficiency +1 | `frontend/hooks/use-lexi.ts` | One round-trip saved on report/compare pages | Low | `Promise.all` |

## Documented, not implemented (with justification)

| Issue | Severity | Why deferred |
|-------|----------|--------------|
| Rate limiting on Gemini-backed endpoints | MEDIUM | Every costly endpoint already requires a verified JWT + per-user ownership; adding a limiter late risks 168 passing tests. Concrete token-bucket design documented in `SECURITY_REPORT_RATE_LIMIT.md` |
| Strict CSP on Next.js app | MEDIUM | Next inline hydration scripts would break under a strict CSP; HSTS+frame-deny+nosniff cover the high-value gaps. Report-only CSP recommended as follow-up |
| Inactive deps (`pyjwt`, `structlog`, `python-dotenv`, dev tools in prod requirements) | LOW | Removal would change CI/Render build steps; zero runtime exposure |
| Supabase composite index `(user_id, created_at)` on documents | LOW | DB-side action; queries already paginate + order server-side |

## Grouping

- **Critical:** none found (no secrets committed, no IDOR, no auth bypass).
- **High:** items 1–7 (implemented).
- **Medium:** items 8–13 (implemented) + deferred items above.
- **Optional:** dependency pruning, report-only CSP, Supabase index, CI `npm audit`/`pip-audit` steps.

## Estimated score movement

- **Security: 85 → 98–99** — headers (FE+BE), CORS tightening, service-key rejection, logging redaction, upload bombs, input sanitization. Remaining gap: rate limiting + strict CSP (documented).
- **Efficiency: 88 → 97–98** — N×1 signed-URL parallelization (biggest win), selective compare fetch, history cap, parallel frontend fetches; all other audited areas verified already-optimal.
- All other categories untouched by code changes (verified: tests, build, lint, typecheck all pass).
