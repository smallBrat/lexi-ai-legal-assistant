# 🎨 Assets

Generated and planned brand assets. SVGs render directly on GitHub.

## Generated (ready to use)

| File | Purpose | Notes |
|---|---|---|
| `architecture.svg` | System architecture | Frontend → Backend → AI/Data layers with guarantees footer |
| `polling-lifecycle.svg` | Polling lifecycle states | startFresh → polling → terminal; 401 retry-once path |
| `upload-pipeline.svg` | Upload & ingestion | validate → store → extract/OCR → chunk |
| `comparison-pipeline.svg` | Comparison pipeline | clause ↔ clause matching → report |
| `rag-flow.svg` | RAG indexing + query | embed → ChromaDB → top-k → grounded answer |
| `auth-flow.svg` | Authentication sequence | Supabase JWT, refresh-once retry-once rule |
| `favicon.svg` | Favicon mark | Scales-of-justice glyph; copy to `frontend/app/icon.svg` to swap the current icon |

Embed in the README (replacing or supplementing the Mermaid versions):

```markdown
![Architecture](docs/assets/architecture.svg)
```

## To generate (specifications)

### 1. OG social preview — `og-image.png`

| Property | Value |
|---|---|
| Size | **1200 × 630 px** (GitHub / social cards standard) |
| Format | PNG or JPG, < 300 KB |
| Background | Deep indigo `#1E1B4B` → `#4338CA` gradient (match favicon) |
| Content | Logo mark (top-left, 96 px) · "Lexi AI" wordmark (Fira Code / Inter, 72 px, white) · tagline *"AI-Powered Legal Assistant & Smart Document Comparator"* (24 px, `#A5B4FC`) · three feature chips: `Risk Analysis` `RAG Chat` `Smart Comparison` |
| Accent | Teal `#2DD4BF` underline on the wordmark |
| Safe zone | Keep text ≥ 60 px from all edges (crop-safe) |

Wire it up: repo **Settings → General → Social preview** → upload the image (GitHub serves it for link unfurls; no code needed).

### 2. Repository banner — `banner.png`

| Property | Value |
|---|---|
| Size | **1600 × 900 px** (also export a 1280 × 640 crop for og:image reuse) |
| Background | Same indigo gradient, subtle scale-of-justice watermark at 8% opacity, right-aligned |
| Content | Logo centered-left (200 px) · project name (120 px) · one-line value prop (28 px) · tech badge row rendered as pill shapes: Next.js 15 · FastAPI · Gemini · LangChain · ChromaDB · Supabase |
| Bottom strip | 6 px teal accent bar across the full width |
| Export | PNG-24; run through squoosh/pngquant to keep < 500 KB |

### 3. Logo — `logo.png`

| Property | Value |
|---|---|
| Size | **512 × 512 px** @2x export from `favicon.svg` vector (transparent background) |
| Usage | README hero (rendered at 140 px) — must survive downscale |
| Palette | `#1E1B4B` indigo, `#4338CA` violet, `#2DD4BF` teal accent, `#A5B4FC` light stroke |

### Recommended tools

- Vector → PNG: [Inkscape](https://inkscape.org), [Figma](https://figma.com), or `inkscape file.svg --export-png=out.png -w 512`
- Optimization: [squoosh.app](https://squoosh.app), `pngquant`
- Mockup text: Inter or Fira Code from Google Fonts
