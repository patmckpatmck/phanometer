import Link from 'next/link';
import { readHistory } from '@/lib/data';
import { BellMeter } from '@/components/BellMeter';
import { Footer } from '@/components/Footer';
import { Header } from '@/components/Header';
import { SeasonTrend, type SeasonMarker } from '@/components/SeasonTrend';
import { formatDateShort } from '@/lib/format';
import { bandFor } from '@/lib/moodBands';
import type { DailyReport } from '@/lib/types';

// OFFSEASON HOMEPAGE (2026–27 winter).
// The daily workflow is disabled until next season, so history.json is frozen
// at the last 2026 reading. This page replaces the daily readout with a
// season-in-review view. The /day/[date] archive pages are unchanged.
// To restore the in-season homepage, revert the commit that introduced this
// file version (git log -- web/app/page.tsx).

const datasetSchema = {
  '@context': 'https://schema.org',
  '@type': 'Dataset',
  name: 'Phan-o-meter Phillies Fan Sentiment Dataset',
  description:
    'Daily fan-mood scores across seven dimensions for the Philadelphia Phillies, derived from podcasts, Reddit, YouTube, and MLB Stats API data. Updated daily during the season.',
  url: 'https://www.phanometer.com',
  keywords: [
    'Philadelphia Phillies',
    'fan sentiment',
    'baseball',
    'MLB',
    'sentiment analysis',
  ],
  creator: {
    '@type': 'Organization',
    name: 'Phan-o-meter',
    url: 'https://www.phanometer.com',
  },
  isAccessibleForFree: true,
  distribution: {
    '@type': 'DataDownload',
    encodingFormat: 'application/json',
    contentUrl:
      'https://raw.githubusercontent.com/patmckpatmck/phanometer/main/data/history.json',
  },
  spatialCoverage: {
    '@type': 'Place',
    name: 'Philadelphia, Pennsylvania, United States',
  },
  temporalCoverage: '2026-04-19/2026-10-04',
  about: {
    '@type': 'SportsTeam',
    name: 'Philadelphia Phillies',
    sameAs: 'https://en.wikipedia.org/wiki/Philadelphia_Phillies',
  },
};

type Scored = DailyReport & { display_score: number };

// "April 19" — sentence-case for body copy (formatDateShort is all-caps).
function formatMonthDay(iso: string): string {
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
  });
}

export default async function Page() {
  const { history, today: finalDay } = await readHistory();
  const first = history[0];
  const scored = history.filter((d): d is Scored => d.display_score != null);

  // First occurrence wins on ties, so "season high" is the day it was reached.
  const high = scored.reduce((a, b) => (b.display_score > a.display_score ? b : a));
  const low = scored.reduce((a, b) => (b.display_score < a.display_score ? b : a));
  const final = scored[scored.length - 1];
  const average = Math.round(
    scored.reduce((sum, d) => sum + d.display_score, 0) / scored.length,
  );
  const avgBand = bandFor(average);

  const markers: SeasonMarker[] = [
    {
      date: high.date,
      score: high.display_score,
      label: `High · ${high.display_score} · ${formatDateShort(high.date)}`,
      place: 'above',
    },
    {
      date: low.date,
      score: low.display_score,
      label: `Low · ${low.display_score} · ${formatDateShort(low.date)}`,
      place: 'below',
    },
    {
      date: final.date,
      score: final.display_score,
      label: `Final · ${final.display_score}`,
      place: 'end',
    },
  ];

  const stats = [
    { k: 'Season average', v: average, sub: avgBand.label },
    { k: 'Season high', v: high.display_score, sub: formatDateShort(high.date) },
    { k: 'Season low', v: low.display_score, sub: formatDateShort(low.date) },
    { k: 'Final reading', v: final.display_score, sub: formatDateShort(final.date) },
  ];

  return (
    <div className="page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(datasetSchema) }}
      />
      <h1 className="sr-only">How Philly felt about the Phillies in 2026.</h1>
      <Header
        today={finalDay}
        metaLines={['How Philly felt about the Phillies', '2026 season · Final']}
      />

      <div className="hero">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="hero-wordmark" src="/assets/wordmark.png" alt="" />
        <BellMeter score={average} />
        <div className="readout">
          <div className="score">{average}</div>
          <div className={`mood mood-${avgBand.slug}`}>{avgBand.label}</div>
          <div className="readout-delta">2026 season average · {scored.length} daily readings</div>
        </div>
      </div>

      <section className="section offseason-note">
        <div className="section-head">
          <span className="section-num">Offseason</span>
          <h2 className="section-title">That&apos;s the 2026 season</h2>
        </div>
        <p className="editor-body">
          Phan-o-meter took Philly&apos;s temperature every day from {formatMonthDay(first.date)}{' '}
          to {formatMonthDay(finalDay.date)}. The meter is off
          for the winter. We&apos;ll be back next season.
        </p>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">01 · The season</span>
          <h2 className="section-title">The meter, start to finish</h2>
        </div>
        <SeasonTrend history={history} markers={markers} />
        <dl className="season-stats">
          {stats.map((s) => (
            <div key={s.k} className="season-stat">
              <dt>{s.k}</dt>
              <dd>
                <span className="season-stat-v">{s.v}</span>
                <span className="season-stat-sub">{s.sub}</span>
              </dd>
            </div>
          ))}
        </dl>
        <p className="season-archive">
          Every day is still on the record:{' '}
          <Link href={`/day/${first.date}`}>opening reading</Link> ·{' '}
          <Link href={`/day/${finalDay.date}`}>final reading</Link>
        </p>
      </section>

      <Footer generatedAt={finalDay.generated_at} />
    </div>
  );
}
