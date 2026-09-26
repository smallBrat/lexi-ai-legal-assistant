# Efficiency Report — Database

## Query-by-query

| Query | Pagination | Selective columns | Ordering | Limits | Index needs |
|-------|-----------|-------------------|----------|--------|-------------|
| `DocumentRepository.list_documents` | `range(start, start+size-1)` with `count="exact"` | explicit column list (no `*`) | server-side `order(sort, desc)` | ≤100 rows | `(user_id, created_at)` — recommend composite index in Supabase (documents.user_id exists via RLS pattern; verify) |
| `DocumentRepository.get_document` | `.limit(1)` | explicit incl. `extracted_text` (needed for detail) | — | 1 | PK |
| `update_document` | `.single()` | explicit | — | 1 | PK + user_id filter (ownership) |
| `delete_document` | 4 child deletes + document delete | — | — | — | FK indexes on `clauses.document_id`, `chat_history.document_id`, `comparisons.document_a_id/b_id` — created by FK constraints in migrations |
| `ChatRepository.get_history` | `.limit(200)` (Phase 15) | explicit | `timestamp asc` | 200 | `(document_id, user_id, timestamp)` — covered by FK index + sort |
| `ComparisonRepository.find_cached` | `.limit(1)` | `*` (row contains `result` JSONB — needed) | `created_at desc` | 1 | unique `(user_id, document_a_id, document_b_id)` from migration |
| `ComparisonRepository.list_for_user` | `.limit(≤50)` | `*` | `created_at desc` | 50 | user_id index |
| `AnalysisService._fetch_document` | `.limit(1)` | explicit incl. heavy `extracted_text` (required for analysis) | — | 1 | PK |

## Vector lookup efficiency

- Chroma collection per `sha256(user_id:document_id)` — retrieval scans one tiny collection, not a global index.
- Query adds `where={"$and":[user_id, document_id]}` even though the collection is already isolated (belt-and-braces).
- `n_results=min(top_k, count)` — no over-fetch.
- Singleton client + persistent client reuse — no per-request Chroma init.

## Findings & actions

1. **Fixed (Phase 15):** chat history unbounded fetch → `limit(200)`.
2. **Recommendation (no code change, Supabase-side):** ensure composite index `(user_id, created_at desc)` on `documents` for the dashboard list sort — most valuable at scale; verify in Supabase SQL editor with `EXPLAIN`.
3. `count="exact"` on list is correct (needed for `total_pages`).

**Verdict: queries are selective, paginated, and ordered server-side; no N+1 patterns.**
