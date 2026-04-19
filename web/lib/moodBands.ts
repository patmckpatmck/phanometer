export interface MoodBand {
  min: number;
  max: number;
  label: string;
  slug: string;
}

export const MOOD_BANDS: readonly MoodBand[] = [
  { min: 90, max: 100, label: 'Red October', slug: 'redoctober' },
  { min: 80, max: 89, label: 'Rally Towel', slug: 'rallytowel' },
  { min: 70, max: 79, label: 'Buzzing', slug: 'buzzing' },
  { min: 60, max: 69, label: 'High Hopes', slug: 'highhopes' },
  { min: 50, max: 59, label: 'Touch and Go', slug: 'touchandgo' },
  { min: 40, max: 49, label: 'Uneasy', slug: 'uneasy' },
  { min: 30, max: 39, label: 'Oh No', slug: 'ohno' },
  { min: 20, max: 29, label: 'Not Again', slug: 'notagain' },
  { min: 10, max: 19, label: 'Meltdown', slug: 'meltdown' },
  { min: 0, max: 9, label: 'Rock Bottom', slug: 'rockbottom' },
];

const UNEASY = MOOD_BANDS[5];

export function bandFor(score: number | null | undefined): MoodBand {
  if (score == null) return UNEASY;
  const s = Math.max(0, Math.min(100, score));
  return MOOD_BANDS.find((b) => s >= b.min && s <= b.max) ?? UNEASY;
}
