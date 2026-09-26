/**
 * Single source of truth for every network timeout in the frontend (PART 5).
 *
 * Why this file exists: `lib/api-client` used to apply one 30s
 * `DEFAULT_TIMEOUT_MS` to every request. Gemini-backed chat routinely needs
 * longer (embedding + retrieval + generation + persistence), so the client
 * aborted healthy in-flight chats at 30s with "Request timed out" while the
 * backend was still working — surfacing as a client-side timeout with no
 * corresponding backend completion log.
 *
 * Policy (do not reuse the analyze timeout for chat):
 *   - CHAT_REQUEST_TIMEOUT_MS .... 300_000 (POST /documents/:id/chat)
 *   - CHAT_HISTORY_TIMEOUT_MS ....  20_000 (GET  /documents/:id/chat)
 *   - DOCUMENT_FETCH_TIMEOUT_MS ..  60_000 (GET  /documents/:id)
 *   - DEFAULT_TIMEOUT_MS .........  30_000 (everything else, incl. analyze)
 *   - Upload uses XHR and is unchanged (no fetch timeout).
 *
 * Backend mirror: `backend/app/services/chat_service.py`
 * `CHAT_GEMINI_TIMEOUT_SECONDS = 120.0`.
 */
export const CHAT_REQUEST_TIMEOUT_MS = 300_000;
export const CHAT_HISTORY_TIMEOUT_MS = 20_000;
export const DOCUMENT_FETCH_TIMEOUT_MS = 60_000;
export const DEFAULT_TIMEOUT_MS = 30_000;
