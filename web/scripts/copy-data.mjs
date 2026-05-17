#!/usr/bin/env node
// Copies ../data → ./data and ../bot_core.py → ./bot_core.py so the Next build
// (and Vercel's Python function bundler) can read both from within the project
// root. Vercel's `includeFiles` glob cannot traverse above the project root, so
// the Python serverless function in api/ask.py needs bot_core.py as a sibling
// inside web/. The copy is build-time only; web/bot_core.py is gitignored to
// prevent drift from the canonical ../bot_core.py.
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
