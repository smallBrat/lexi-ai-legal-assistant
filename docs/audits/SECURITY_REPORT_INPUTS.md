# Security Report — Input Validation

## Schema coverage (every endpoint)

| Endpoint | Schema / validation | Verdict |
|----------|--------------------|---------|
| `POST /upload` | `DocumentType` enum (Form), title length ≤200 + control-char rejection (now **ANSI/C1 stripping**), file controls per upload report | PASS |
| `GET /documents` | `page ge=1`, `page_size 1..100`, `search max_length=100` + **sanitized** (Phase 15), enum-validated `document_type/status/sort/order`, `risk_level` allowlist | PASS |
| `PATCH /documents/{id}` | `DocumentUpdateRequest` — `extra="forbid"`, title ≤200 with validator | PASS |
| `POST /analyze/{id}` | UUID path param; `force` bool Query | PASS |
| `POST /chat` | `ChatRequest` — `extra="forbid"`, `question 1..4000`, **new control-character validator** (Phase 15) | HARDENED |
| `POST /documents/{id}/chat` | `ChatQuestionRequest` — same validators | HARDENED |
| `POST /compare` | `CompareRequest` — `extra="forbid"`, UUIDs; self-compare → 422 | PASS |

## Injection classes

| Class | Exposure | Mitigation |
|-------|----------|-----------|
| SQL injection | None — all DB access via Supabase postgrest client builder (`eq/ilike/range`), parameterized | PASS. `search` goes into `ilike("title", f"%{search}%")`; `%`/`_` wildcards could over-match but cannot inject; Phase 15 sanitization strips control chars and clamps length |
| NoSQL injection | N/A (Postgres) | PASS |
| Header injection | No user input reflected into headers; static security headers only | PASS |
| XSS | React auto-escapes; no `dangerouslySetInnerHTML` in repo (verified); backend returns JSON only | PASS |
| HTML/Markdown injection | Analysis text rendered as React text nodes, never as raw HTML/Markdown-to-HTML | PASS |
| Log forging / terminal escape | Titles & search now strip ANSI CSI/OSC sequences and C0/C1 controls (`app/utils/sanitize.py`) — **Phase 15** | FIXED |
| Prompt-length abuse | Question ≤4,000 chars; context excerpts bounded by retrieval `top_k=5` and `EMBEDDING_MAX_INPUT_CHARS` | PASS |

## Prompt injection → see SECURITY_REPORT_AI.md (dedicated RAG analysis).

**Risk: LOW after Phase 15.**
