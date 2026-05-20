import type { MetadataRoute } from 'next';

// Required when next.config.ts sets output: 'export' — opts the
// generated sitemap.xml route into the static export pipeline.
export const dynamic = 'force-static';

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  // Static recent date for pages that don't change daily.
  // Bump this manually when content meaningfully changes.
  const evergreen = new Date('2026-05-19');

  return [
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
}
