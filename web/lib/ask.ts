// Shared helpers for the Ask the Crowd feature.
//
// The /api/ask endpoint streams plain text and emits no metadata, so the
// permalink slug and the corpus footnote stats are both computed on the
// frontend instead. See the README in design_handoff_ask_the_crowd/ for the
// original (SSE-based) design and the prompt that ships this build for the
// substitutions used here.

import type { DailyReport } from './types';

/**
 * Slugify a question for display in the signature line.
 *
 * The actual permalink uses ?q=<url-encoded raw text>, not the slug. The slug
 * is purely a display affordance ("phanometer.com/ask/<slug>"). Algorithm:
 * lowercase, hyphenate whitespace and non-alphanumerics, strip remaining
 * punctuation, cap at ~60 chars at a word boundary.
 */
export function slugify(question: string): string {
  const lowered = question.toLowerCase().trim();
  // Replace runs of non-alphanumeric (excluding hyphen) with a single hyphen.
  let slug = lowered.replace(/[^a-z0-9]+/g, '-');
  // Collapse multiple hyphens and trim leading/trailing.
  slug = slug.replace(/-+/g, '-').replace(/^-+|-+$/g, '');
  // Cap at ~60 chars on a word boundary.
  if (slug.length > 60) {
    const truncated = slug.slice(0, 60);
    const lastHyphen = truncated.lastIndexOf('-');
    slug = lastHyphen > 30 ? truncated.slice(0, lastHyphen) : truncated;
  }
  return slug;
}

export interface CorpusStats {
  podcastEpisodes: number;
  dailyReadings: number;
  dateFrom: string; // "April 15"
  dateTo: string; // "May 17"
}

/**
 * Format an ISO date string ("2026-05-09") as "Month D" ("May 9").
 * Uses UTC parsing so the displayed month/day match the canonical date in the
 * history record regardless of the renderer's local timezone.
 */
function formatMonthDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toLocaleString('en-US', {
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/**
 * Derive the four signature-line footnote values from the daily history.
 * Sorted-ascending history is expected (matches what lib/data.ts returns).
 */
export function getCorpusStats(history: DailyReport[]): CorpusStats {
  const podcastEpisodes = history.reduce(
    (sum, day) => sum + (day.source_counts?.podcasts_transcribed ?? 0),
    0,
  );
  return {
    podcastEpisodes,
    dailyReadings: history.length,
    dateFrom: formatMonthDay(history[0].date),
    dateTo: formatMonthDay(history[history.length - 1].date),
  };
}

// Fixed example questions. Not user-editable — the voice calibration is the
// design. Order is the display order.
export const HOMEPAGE_EXAMPLES: readonly string[] = [
  'How has the mood shifted since the 10-3 stretch?',
  'What was the worst day on record?',
  'How have fans felt about Bohm this season?',
];

export const ASK_PAGE_EXAMPLES: readonly string[] = [
  'How has the mood shifted since the 10-3 stretch?',
  'What was the worst day on record?',
  'How have fans felt about Bohm this season?',
  'When was the last time pitching confidence cracked 80?',
  "Who's getting roasted most this month?",
];
