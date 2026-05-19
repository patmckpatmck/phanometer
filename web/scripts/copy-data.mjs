#!/usr/bin/env node
// Copies repo-root artifacts into web/ before every Next.js build so the
// static export and the Python serverless function bundler can reach them
// from within the project root. Vercel's `includeFiles` glob cannot traverse
// above the project root, so anything the deploy needs has to live under
// web/ at build time.
//
// Sources copied:
//   ../data           → ./data            (history.json for /api/ask)
//   ../bot_core.py    → ./bot_core.py     (shared with api/ask.py)
//   ../reels          → ./public/reels    (daily social-media reels;
//                                          built by reel/build.py, served at
//                                          phanometer.com/reels/*.html)
//
// All three destinations are gitignored to prevent drift from the canonical
// sources at the repo root.
//
// Run as `pnpm copy-data` (chained from `dev` / `build` scripts in package.json).

import { cp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

const dataSrc = path.resolve(here, '../../data');
const dataDest = path.resolve(here, '../data');
const botCoreSrc = path.resolve(here, '../../bot_core.py');
const botCoreDest = path.resolve(here, '../bot_core.py');
const reelsSrc = path.resolve(here, '../../reels');
const reelsDest = path.resolve(here, '../public/reels');

if (!existsSync(dataSrc)) {
  console.error(`[copy-data] source directory missing: ${dataSrc}`);
  process.exit(1);
}
if (!existsSync(botCoreSrc)) {
  console.error(`[copy-data] source file missing: ${botCoreSrc}`);
  process.exit(1);
}

await rm(dataDest, { recursive: true, force: true });
await cp(dataSrc, dataDest, { recursive: true });
console.log(`[copy-data] ${path.relative(process.cwd(), dataSrc)} → ${path.relative(process.cwd(), dataDest)}`);

await rm(botCoreDest, { force: true });
await cp(botCoreSrc, botCoreDest);
console.log(`[copy-data] ${path.relative(process.cwd(), botCoreSrc)} → ${path.relative(process.cwd(), botCoreDest)}`);

// reels/ is optional — if reel/build.py has never run yet, skip silently so
// a fresh checkout can still build the site. The directory will appear after
// the first nightly cron and be picked up on the next build.
await rm(reelsDest, { recursive: true, force: true });
if (existsSync(reelsSrc)) {
  await cp(reelsSrc, reelsDest, { recursive: true });
  console.log(`[copy-data] ${path.relative(process.cwd(), reelsSrc)} → ${path.relative(process.cwd(), reelsDest)}`);
} else {
  console.log(`[copy-data] no ${path.relative(process.cwd(), reelsSrc)} yet — skipping reels copy`);
}
