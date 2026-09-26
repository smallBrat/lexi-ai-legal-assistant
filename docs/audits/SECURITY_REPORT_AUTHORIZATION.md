# Security Report — Authorization (IDOR Sweep)

Every route was traced end-to-end (API handler → service → repository → SQL filter).

## Route-by-route ownership matrix

| Route | Method | Ownership enforcement | Verdict |
|-------|--------|----------------------|---------|
| `/upload` | POST | `user_id` from JWT set server-side on insert; storage path is a fresh UUID (no client input in path) | PASS |
| `/documents` | GET | Repository filters `.eq("user_id", user_id)`; pagination `1..100` per page | PASS |
| `/documents/{id}` | GET | Fetch by id → service compares `row.user_id` to JWT user → 403/404 | PASS |
| `/documents/{id}` | PATCH | Service loads owned doc first, then update query re-filters `.eq("user_id", ...)` | PASS (double-checked) |
| `/documents/{id}` | DELETE | Owned fetch first; final delete re-filters `.eq("user_id", ...)`; child-table deletes scoped by `document_id` which was just proven owned | PASS |
| `/documents/{id}/signed-url` | GET | Owned fetch first (`get_document(document_id, user_id)`), URL minted only for `document.storage_path` | PASS — cannot obtain others' signed URLs |
| `/analyze/{id}` | POST/GET | `_fetch_document` filters `.eq("id").eq("user_id")` in SQL — no post-hoc check to bypass | PASS |
| `/chat`, `/documents/{id}/chat` | POST | `get_document(document_id, user_id)` then explicit `user_id` comparison → `ChatForbiddenError` → 403 | PASS |
| `/chat/{id}` history | GET/DELETE | Same ownership gate before repository access | PASS |
| `/compare` | POST | `CompareService._load_validated` compares `row.user_id` for **both** documents; cache lookup filters `.eq("user_id", user_id)` | PASS |
| `/compare` | GET | `list_for_user` filters `.eq("user_id", user_id)` | PASS |
| `/health`, `/` | GET | Public by design, no data | PASS |

## Specific attack scenarios checked

1. **IDOR via document UUID** — all reads/writes either filter by `user_id` in SQL or compare the fetched row's `user_id` to the JWT subject. ❌ blocked
2. **Signed URL of another user's file** — storage paths are `{uuid}.{ext}` minted server-side at upload; signed-url endpoint requires ownership first. ❌ blocked
3. **Cross-user ChromaDB retrieval** — collection name is `sha256(user_id:document_id)` and queries add `where={"user_id": ..., "document_id": ...}`. ❌ blocked
4. **Comparisons across users** — cache key includes `user_id`; both documents must be owned. ❌ blocked
5. **Pagination leakage** — every list query is user-scoped before `range()`/`limit()`. ❌ blocked
6. **Chat history IDOR** — history endpoints gate on document ownership; repository additionally filters `.eq("user_id", user_id)`. ❌ blocked

## Phase 15 additions

- Chat history GET now hard-capped at 200 rows (`limit(200)`) — bounds unbounded-growth DoS without changing the contract (frontend renders the latest exchanges; typical histories are far smaller).

**IDOR vulnerabilities found: 0.**
