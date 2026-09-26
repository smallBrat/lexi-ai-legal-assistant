# Security Report — HTTP Surface

## Security headers — BACKEND (Phase 15: FIXED)

New `app/core/middleware.py` (`SecurityHeadersMiddleware`) applies to **every** backend response:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'` (JSON API — nothing is served for browsers to execute) |

## Security headers — FRONTEND (Phase 15: FIXED)

`next.config.mjs` now returns `headers()` for `/:path*`:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` |

A full CSP for the Next.js app was deliberately **not** imposed: the app uses Next inline bootstrap/hydration scripts, and a too-strict CSP would break the deployed UI (violates "preserve every feature"). HSTS + frame-deny + nosniff cover the highest-value gaps. Tightening a report-only CSP is listed in the master plan as optional.

## CORS — BACKEND (Phase 15: HARDENED)

Before: `allow_origins=[localhost:3000, 127.0.0.1:3000, FRONTEND_URL]`, `allow_methods=["*"]`, `allow_headers=["*"]`.

After:
- Origins unchanged (explicit allowlist — no wildcard; correct because `allow_credentials=True` forbids `*` anyway).
- **Methods** restricted to `GET, POST, PUT, PATCH, DELETE, OPTIONS`.
- **Headers** restricted to `Authorization, Content-Type, Accept, Origin, X-Requested-With`.
- **`max_age=600`** — pre-flights cached, cutting OPTIONS round-trips (also an efficiency win).

## Cookies

- Backend is stateless JWT (Authorization header) — no cookies set by the API.
- Frontend uses Supabase JS with `localStorage` (no cookies) — default `SameSite` concerns do not apply; CSRF surface is nil because the backend never accepts cookie credentials.

## Cache-Control

- Backend: all responses are dynamic JSON; no caching layers in front on Render — no action needed. Health endpoint is polled and uncached (`cache: "no-store"` on the Next proxy).
- Frontend: static assets are content-hashed by Next (immutable caching by default).

**Risk: LOW after Phase 15.**
