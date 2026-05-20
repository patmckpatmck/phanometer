// Shared helpers for the Ask the Crowd feature.

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

// Fixed example questions. Not user-editable — the voice calibration is the
// design. Order is the display order.
export const HOMEPAGE_EXAMPLES: readonly string[] = [
  'How has the mood shifted in the past week?',
  'What was the worst day on record?',
  'How have fans felt about Bohm this season?',
];

export const ASK_PAGE_EXAMPLES: readonly string[] = [
  'How has the mood shifted in the past week?',
  'What was the worst day on record?',
  'How have fans felt about Bohm this season?',
  'When was the last time pitching confidence cracked 80?',
  "Who's getting roasted most this month?",
];
