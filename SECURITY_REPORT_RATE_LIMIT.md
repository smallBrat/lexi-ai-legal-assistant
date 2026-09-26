# Security Report — Rate Limiting

## Current state

No rate limiter exists on any endpoint. Exposure per endpoint:

| Endpoint | Cost | Abuse scenario |
|----------|------|----------------|
| `POST /upload` | 20 MB parse + OCR (up to 100 pages) | storage/DB churn, OCR CPU burn |
| `POST /analyze/{id}` | Gemini call (multi-model, up to ~120s) | **API quota drain** (highest impact) |
| `POST /chat`, `/documents/{id}/chat` | embedding + vector search + Gemini (~150s budget) | **API quota drain** |
| `POST /compare` | two document loads + Gemini | quota drain |
| `GET /health` | trivial | negligible |

All endpoints require a **verified Supabase JWT**, so an attacker needs accounts — the auth gate is itself a rate limiter of last resort. Document endpoints are additionally per-user scoped (a user can only burn their own analysis cache).

## Recommendation (documented, deliberately not implemented in Phase 15)

A lightweight, dependency-free in-process limiter fits this architecture (single uvicorn worker on Render free tier):

```python
# sketch — per-user token bucket keyed by (user_id, route-class)
from collections import defaultdict, deque
import time

LIMITS = {  # class: (max_events, window_seconds)
    "analyze": (10, 60),   # analyze + chat + compare: Gemini-backed
    "upload":  (10, 60),
    "read":    (120, 60),  # GETs: generous
}
```

- Middleware or dependency reading `current_user.id` after `get_current_user`, returning `429` with `Retry-After`.
- `deque`-based sliding window per key; O(1) memory per active user; no Redis needed at this scale.

### Why not implemented now

1. Render free tier runs a **single process** — an in-process limiter would be accurate, but adding a new middleware + tests late in the cycle risks regressions in all 168 passing tests for marginal gain (every endpoint already requires JWT + ownership).
2. `slowapi`/`limits` would add a new production dependency — violates the minimal-change rule.
3. The Gemini-side failure modes are already bounded: per-request timeouts, model fallback caps, and structured 503/429 mapping.

**Verdict: gap documented with a concrete fix strategy; risk MEDIUM, mitigated by mandatory JWT auth on every costly endpoint.**
