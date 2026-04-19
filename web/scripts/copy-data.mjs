#!/usr/bin/env node
// Copies ../data → ./data so the Next build can read JSON from within the project root.
// Run as `pnpm copy-data` (chained from `dev` / `build` scripts in package.json).

import { cp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '../../data');
const dest = path.resolve(here, '../data');

if (!existsSync(src)) {
  console.error(`[copy-data] source directory missing: ${src}`);
  process.exit(1);
}

await rm(dest, { recursive: true, force: true });
await cp(src, dest, { recursive: true });

console.log(`[copy-data] ${path.relative(process.cwd(), src)} → ${path.relative(process.cwd(), dest)}`);
