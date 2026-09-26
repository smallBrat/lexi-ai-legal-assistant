# Security Report — Dependencies

## Frontend (`package.json`)

| Dependency | Role | Status |
|------------|------|--------|
| next ^15.5.25 | framework | current 15.x line |
| react / react-dom ^19.1.0 | UI | current |
| @supabase/supabase-js ^2.116.0 | auth | current major |
| @tanstack/react-query ^5.59.0 | data cache | current major |
| framer-motion ^11.11.9 | animation | current major |
| zod ^3.23.8, react-hook-form, @hookform/resolvers | validation/forms | current major |
| lucide-react ^0.453.0 | icons | current; imported via `optimizePackageImports` (tree-shaken) |

- No duplicate libraries detected (one animation lib, one validation lib, one data lib, one state lib).
- No deprecated packages in use.
- `npm audit` note: run `npm audit` in CI to catch transitive advisories over time — recommended follow-up, no current known blockers.

## Backend (`requirements.txt`)

| Package | Role | Status |
|---------|------|--------|
| fastapi, uvicorn[standard], python-multipart | API | current |
| pydantic, pydantic-settings | validation | current major |
| supabase, google-genai, chromadb | data/AI | current |
| PyMuPDF, Pillow | parsing | **keep current** — parser CVEs are the classic upload vector; both are regularly patched |
| pyjwt[crypto] | *unused placeholder* (Supabase Auth API verification is used instead) | flagged |
| structlog | *unused* — the project has its own `core/logging.py` | flagged |
| python-dotenv | redundant with pydantic-settings | flagged |
| pytest, pytest-asyncio, ruff, black | dev tooling installed in production requirements | flagged |

### Unused-dependency findings (LOW risk, optional cleanup)

1. `pyjwt[crypto]` — nothing imports `jwt`. Either keep (documented as the opt-in HS256 path) or move to a `requirements-dev.txt`.
2. `structlog` — unused; the structured logger is homegrown. Removable.
3. `python-dotenv` — pydantic-settings already loads `.env`. Removable.
4. Dev tools (`pytest*`, `ruff`, `black`) live in the same file that production installs on Render. Splitting into `requirements-dev.txt` would shrink the production image and reduce supply-chain surface. **Left in place to preserve the existing CI/Render build commands unchanged.**

These are the only findings; all are LOW. No vulnerable versions are pinned anywhere.

**Risk: LOW.**
