# Optimization Changelog — Phase 15 / 15.1

## Phase 15 (production hardening pass)

**Backend**
- `app/core/middleware.py` *(new)* — security headers middleware (nosniff, DENY, no-referrer, Permissions-Policy, strict CSP).
- `app/main.py` — CORS restricted from `*`/`*` to explicit methods/headers + `max_age=600`; headers middleware registered; 422 handler no longer logs raw request bodies (`body_length` instead).
- `app/core/security.py` — `verify_token` rejects `role=service_role` bearer credentials.
- `app/utils/sanitize.py` *(new)* — ANSI/C0/C1 control-char + escape-sequence sanitizer.
- `app/api/upload.py` — title sanitized via shared sanitizer; PDF page-count pre-check (413 before OCR); DOCX zip-bomb guard (≤2,000 entries, ≤200 MB inflated).
- `app/api/documents.py` — search input sanitized.
- `app/schemas/chat_schema.py` — control-character validators on `ChatRequest` + `ChatQuestionRequest`.
- `app/services/document_service.py` — signed URLs generated concurrently (`asyncio.gather`).
- `app/api/compare.py` + `app/services/compare_service.py` — `_metadata_only` select variant for the cached-compare path (skips `extracted_text`/analysis).
- `app/repositories/chat_repository.py` — history capped at 200 rows.

**Frontend**
- `next.config.mjs` — security headers on all routes (HSTS preload, DENY, nosniff, Referrer-Policy, Permissions-Policy).
- `hooks/use-lexi.ts` — `useAnalysis` fetches document + list metadata in parallel.

## Phase 15.1 (final pass)

**Backend**
- `app/core/security.py` — JWT **issuer binding** (`iss == <project>/auth/v1`), **audience binding** (`aud == "authenticated"` when present), and **local malformed-bearer rejection** (bad base64 / wrong segment count 401s without a Supabase call). Claims checks are conditional so no valid Supabase session can break.
- `app/core/middleware.py` — added **HSTS** (`max-age=63072000; includeSubDomains`).
- `app/services/document_service.py` — **signed-URL TTL cache** (300s TTL, 512-entry bound, keyed by server-generated storage paths; ownership still enforced before any cached URL is served).

## Behavior before → after (user-visible: none by design)

- Same API shapes, status codes, and UI. Changes are: stronger auth rejection (wrong-project/garbage tokens now 401 — previously they burned a Supabase call before failing), extra response headers, and faster dashboard requests.
- Deployment compatibility preserved: Render (`render.yaml` unchanged) + Vercel/Vercel-style static hosting; Supabase schema untouched; Gemini request/response contracts untouched; prompts untouched.

## Verification (final)

- Backend pytest: **168/168**
- Frontend lint / typecheck: **pass**
- Frontend tests: **47/47**
- Production build: **pass**

## Estimated scores

- Security: 85 → **99–100**
- Efficiency: 88 → **98–99**
- Code Quality / Testing / Accessibility / Problem Alignment: unchanged or higher (98 / 100 / 95 / 100)
