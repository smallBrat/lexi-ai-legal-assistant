# Lexi AI Legal Workspace — Frontend

Production-ready Next.js 15 (App Router) application generated from the Google Stitch project
**Lexi AI Legal Workspace** (`3906199904898572878`).

## Source design

- Stitch project metadata + design tokens: `frontend/.stitch/project.json`
- Per-screen HTML/CSS: `frontend/.stitch/html/*.html`
- Screen thumbnails: `frontend/.stitch/images/*`
- Screen inventory: `frontend/.stitch/manifest.json`
- Design tokens (Geist type, `#1e32df` primary, Material-3 style surfaces) are encoded in
  `tailwind.config.ts` and `app/globals.css`.

## Setup

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

## Routes

| Route | Screen |
| --- | --- |
| `/` | Landing Page |
| `/auth` | Authentication |
| `/upload` | Upload Workspace |
| `/processing` | Processing Experience |
| `/dashboard` | Document Dashboard |
| `/dashboard/[id]` | Clause Explorer + Plain English + AI Chat (tabbed) |
| `/compare` | Compare Documents Upload |
| `/compare/results` | Comparison Results |
| `/rights` | Know Your Rights |
| `/report` | Export Report + Lawyer Preparation Pack |
| `/saved` | Saved Documents |
| `/settings` | Settings & Accessibility |

## Data layer

Typed service placeholders under `services/` (`documents`, `analysis`, `chat`, `compare`,
`rights`, `report`) return typed mock data from `lib/mock-data.ts`, which mirrors the backend
contract in `backend/app/schemas/analysis_schema.py`. Swap each service body for a `fetch`
call when the API is ready — component code does not need to change.

## Scripts

- `npm run dev` — local development
- `npm run build` / `npm start` — production build & serve
- `npm run typecheck` — strict TypeScript check

## Notes

- Lexi provides general information, not legal advice; the disclaimer is in the site footer.
- Animations respect `prefers-reduced-motion`. Touch targets are ≥ 44px. Forms are keyboard
  navigable with labelled controls and `aria-live` upload/chat status.
