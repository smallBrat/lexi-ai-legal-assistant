# Security Report — Logging

## Verified across all backend log sites (`core/logging.py` + every caller)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| No secrets logged | PASS | API keys only via `SecretStr` in Settings; `repr`/`str` of settings never logged |
| No JWT logged | PASS | Authorization header redacted to `Bearer <redacted>` in `main.py` before logging |
| No API responses logged | PASS | Gemini responses logged as **metadata only** (`summarize_response`: token counts, finish reason, `text_chars` — never the text) |
| No uploaded document text logged | PASS | Upload pipeline logs filenames, ids, page/char counts. **Phase 15: the 422 validation-error handler no longer logs request bodies** (it previously dumped `body.decode()` — chat questions/uploads could reach logs); now logs `body_length` only. Chat retrieval logs `query[:500]` (question snippet) — bounded and user's own data; document excerpts are logged only as titles, never full text |
| No embeddings logged | PASS | Only dimensions/elapsed logged |
| No PII logged | PASS | User identity logged as `user_id` (UUID) only |

## Structured logging

- Single structured formatter: `[LEVEL] name - message (timestamp)` with key-value context on every call — already structured (Render captures stdout; file logging disabled in production).
- Error logs carry `exc_type`/`exc_message`/traceback for infrastructure failures — no client-controlled payloads beyond ids/lengths.

## Phase 15 change

`backend/app/main.py` — `RequestValidationError` handler: `body=...` → `body_length=len(body)`. Reason: the old handler logged the **full raw request body** on 422s; for the chat compatibility endpoint the body contains the user's question, and for uploads nothing at all (multipart bodies are opaque, but the pattern was unsafe). Length-only logging preserves debuggability.

**Risk: LOW after Phase 15.**
