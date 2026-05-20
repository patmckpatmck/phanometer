import type { MetadataRoute } from 'next';
import { readHistory } from '@/lib/data';

// Required when next.config.ts sets output: 'export' — opts the
// generated sitemap.xml route into the static export pipeline.
export const dynamic = 'force-static';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  // Static recent date for pages that don't change daily.
  // Bump this manually when content meaningfully changes.
  const evergreen = new Date('2026-05-19');

  const staticUrls: MetadataRoute.Sitemap = [
    {
      url: 'https://www.phanometer.com/',
      lastModified: now,
      changeFrequency: 'daily',
      priority: 1.0,
    },
    {
      url: 'https://www.phanometer.com/ask',
      lastModified: now,
      changeFrequency: 'daily',
      priority: 0.8,
    },
    {
      url: 'https://www.phanometer.com/reels/about',
      lastModified: evergreen,
      changeFrequency: 'monthly',
      priority: 0.5,
    },
  ];

  // One entry per historical day. Each archive is content-frozen after its
  // generation date — the cron only writes new days, never rewrites old
  // ones — so a `yearly` change frequency is honest.
  const { history } = await readHistory();
  const archiveUrls: MetadataRoute.Sitemap = history.map((entry) => ({
    url: `https://www.phanometer.com/day/${entry.date}`,
    lastModified: new Date(entry.generated_at),
    changeFrequency: 'yearly',
    priority: 0.6,
  }));

  return [...staticUrls, ...archiveUrls];
}
