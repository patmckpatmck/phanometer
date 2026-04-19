import { readFile } from 'node:fs/promises';
import path from 'node:path';
import type { DailyReport } from './types';

export interface HistoryBundle {
  history: DailyReport[];
  today: DailyReport;
}

// Build-time read. `scripts/copy-data.mjs` places history.json at <web>/data.
export async function readHistory(): Promise<HistoryBundle> {
  const file = path.resolve(process.cwd(), 'data', 'history.json');
  const raw = await readFile(file, 'utf8');
  const parsed = JSON.parse(raw) as DailyReport[];

  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new Error(`history.json at ${file} is empty or malformed`);
  }

  const history = [...parsed].sort((a, b) => a.date.localeCompare(b.date));
  const today = history[history.length - 1];

  return { history, today };
}
