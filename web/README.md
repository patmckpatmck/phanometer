# phanometer-web

Static Next.js 15 (App Router) frontend for Phan-o-meter. Deployed to Vercel as a static export.

## Data flow

`pnpm copy-data` copies `../data/` → `./data/` before `dev`/`build`. Pages read `./data/history.json` at build time and bake into static HTML. Nightly `phanometer.py` runs commit JSON updates; pushing to `main` triggers Vercel to rebuild and redeploy.

## Develop

```bash
pnpm install
pnpm dev
```

## Build static export

```bash
pnpm build
# outputs to ./out
```

## Vercel config

- Project root: `web/`
- Build command: `pnpm build`
- Output directory: `out`
- Node version: 22
