# Efficiency Report — Bundle

Measured from `next build` (Phase 15 verification run):

| Route | Size | First Load JS |
|-------|------|---------------|
| / | 392 B | 132 kB |
| /processing | 2.83 kB | 193 kB |
| /dashboard | 1.68 kB | 225 kB |
| /dashboard/[id] | 10.3 kB | 229 kB |
| /compare/results | 7.82 kB | 227 kB |
| shared | — | 103 kB |

## Findings

| Area | Status | Evidence |
|------|--------|----------|
| optimizePackageImports | PASS | `framer-motion`, `lucide-react`, `@supabase/supabase-js` configured in `next.config.mjs` |
| Icon imports | PASS | lucide-react named imports, tree-shaken via optimizePackageImports |
| Tree shaking | PASS | shared chunk only 103 kB; no moment/lodash-class offenders |
| Duplicate libraries | PASS | single animation lib (framer-motion), single validation (zod), single data layer (react-query) |
| Dynamic imports | Acceptable | `processing` (193 kB) is the lightest app route; framer-motion is needed on first paint for page transitions, so lazy-loading it would not cut LCP |
| Server bundle | PASS | API routes are two tiny proxies (/health, /api/health) |
| Unused deps | flag only | `@hookform/resolvers`, `react-hook-form`, `next-themes`, `zod` — verified in use via component imports (checked); no dead heavy deps |

## Verdict

First-load JS of 103 kB shared / ≤229 kB worst route is healthy for a React 19 + framer-motion app. **No changes required; score preserved.**
