import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { readHistory } from '@/lib/data';
import { Attendance } from '@/components/Attendance';
import { DayNav } from '@/components/DayNav';
import { Dimensions } from '@/components/Dimensions';
import { Footer } from '@/components/Footer';
import { Header } from '@/components/Header';
import { Hero } from '@/components/Hero';
import { HomeAskSection } from '@/components/HomeAskSection';
import { Quotes } from '@/components/Quotes';
import { Themes } from '@/components/Themes';
import { Trend } from '@/components/Trend';
import type { DailyReport } from '@/lib/types';

// Required for next.config.ts `output: 'export'` to emit a static HTML file
// per generated param.
export const dynamic = 'force-static';

// Long-form date without the weekday — used in titles, headlines, and the
// sr-only h1. Matches "May 15, 2026" rather than the homepage masthead's
// "Tuesday, May 15, 2026".
function formatDateLong(iso: string): string {
  const d = new Date(iso + 'T12:00:00');
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

// Pull the first sentence of free-form prose. Mirrors the homepage's
// `firstSentence` helper so the description fallback behaves identically.
function firstSentence(text: string): string {
  const parts = text.match(/[^.!?]+[.!?]+(\s|$)/g);
  return (parts?.[0] ?? text).trim();
}

const DESCRIPTION_FALLBACK =
  'A daily Phan-o-meter readout of Philadelphia Phillies fan mood, scored from podcasts, Reddit, YouTube, and MLB Stats API data.';

function describe(entry: DailyReport): string {
  const candidate = entry.vibe_summary ?? firstSentence(entry.reasoning ?? '');
  return candidate.trim().length > 0 ? candidate : DESCRIPTION_FALLBACK;
}

interface PageProps {
  // Next.js 15: params is async.
  params: Promise<{ date: string }>;
}

export async function generateStaticParams(): Promise<{ date: string }[]> {
  const { history } = await readHistory();
  return history.map((h) => ({ date: h.date }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { date } = await params;
  const { history } = await readHistory();
  const entry = history.find((h) => h.date === date);
  if (!entry) {
    return {};
  }

  const formattedDate = formatDateLong(date);
  const title = `Phillies fan mood — ${formattedDate}`;
  const description = describe(entry);
  const url = `https://www.phanometer.com/day/${date}`;

  return {
    title: { absolute: `${title} — Phan-o-meter` },
    description,
    alternates: { canonical: `/day/${date}` },
    openGraph: {
      type: 'article',
      title,
      description,
      url,
      images: [
        {
          url: '/assets/og-default.png',
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: ['/assets/og-default.png'],
    },
  };
}

export default async function DayPage({ params }: PageProps) {
  const { date } = await params;
  const { history } = await readHistory();
  const idx = history.findIndex((h) => h.date === date);
  if (idx === -1) {
    notFound();
  }

  const entry = history[idx];
  const previous = idx > 0 ? history[idx - 1] : undefined;
  const formattedDate = formatDateLong(date);
  const description = describe(entry);

  // Article JSON-LD — one per archive page, in addition to the WebSite
  // schema from the root layout. Search engines treat each archive as a
  // dated article about that day's fan mood.
  const articleSchema = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: `Phillies fan mood — ${formattedDate}`,
    description,
    datePublished: entry.generated_at,
    dateModified: entry.generated_at,
    author: {
      '@type': 'Organization',
      name: 'Phan-o-meter',
      url: 'https://www.phanometer.com',
    },
    publisher: {
      '@type': 'Organization',
      name: 'Phan-o-meter',
      url: 'https://www.phanometer.com',
      logo: {
        '@type': 'ImageObject',
        url: 'https://www.phanometer.com/assets/wordmark.png',
      },
    },
    mainEntityOfPage: {
      '@type': 'WebPage',
      '@id': `https://www.phanometer.com/day/${date}`,
    },
    about: {
      '@type': 'SportsTeam',
      name: 'Philadelphia Phillies',
      sameAs: 'https://en.wikipedia.org/wiki/Philadelphia_Phillies',
    },
    image: 'https://www.phanometer.com/assets/og-default.png',
  };

  return (
    <div className="page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(articleSchema) }}
      />
      <h1 className="sr-only">Phillies fan mood — {formattedDate}</h1>
      <Header today={entry} />
      <DayNav history={history} currentIndex={idx} />
      <Hero today={entry} />

      <section className="section">
        <div className="section-head">
          <span className="section-num">01 · Trend</span>
          <h2 className="section-title">The last 30 days</h2>
        </div>
        <Trend history={history} todayScore={entry.display_score} todayIndex={idx} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">02 · The vibe</span>
          <h2 className="section-title">How Philly felt about the Phillies, that day</h2>
        </div>
        <p className="editor-body">{description}</p>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">03 · The count</span>
          <h2 className="section-title">The scoring dimensions</h2>
        </div>
        <Dimensions
          dimensions={entry.dimensions}
          confidence={entry.dimension_confidence}
          previousDimensions={previous?.dimensions}
        />
      </section>

      <HomeAskSection />

      <section className="section">
        <div className="section-head">
          <span className="section-num">05 · Cheers &amp; groans</span>
          <h2 className="section-title">What was working and what was not</h2>
        </div>
        <Themes themes={entry.themes} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">06 · In the air</span>
          <h2 className="section-title">Hot takes from fans, journalists, and loudmouths</h2>
          <div className="section-sub">*As read by Phan-o-meter</div>
        </div>
        <Quotes today={entry} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">07 · At the gate</span>
          <h2 className="section-title">Attendance</h2>
        </div>
        <Attendance att={entry.hard_signals?.attendance} />
      </section>

      <DayNav history={history} currentIndex={idx} />
      <Footer generatedAt={entry.generated_at} />
    </div>
  );
}
