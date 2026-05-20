import { readHistory } from '@/lib/data';
import { Attendance } from '@/components/Attendance';
import { Dimensions } from '@/components/Dimensions';
import { Footer } from '@/components/Footer';
import { Header } from '@/components/Header';
import { Hero } from '@/components/Hero';
import { HomeAskSection } from '@/components/HomeAskSection';
import { Quotes } from '@/components/Quotes';
import { Themes } from '@/components/Themes';
import { Trend } from '@/components/Trend';

const datasetSchema = {
  '@context': 'https://schema.org',
  '@type': 'Dataset',
  name: 'Phan-o-meter Phillies Fan Sentiment Dataset',
  description:
    'Daily fan-mood scores across seven dimensions for the Philadelphia Phillies, derived from podcasts, Reddit, YouTube, and MLB Stats API data. Updated nightly.',
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
  temporalCoverage: '2026-04-19/..',
  about: {
    '@type': 'SportsTeam',
    name: 'Philadelphia Phillies',
    sameAs: 'https://en.wikipedia.org/wiki/Philadelphia_Phillies',
  },
};

function firstSentence(text: string): string {
  const parts = text.match(/[^.!?]+[.!?]+(\s|$)/g);
  return (parts?.[0] ?? text).trim();
}

export default async function Page() {
  const { history, today } = await readHistory();
  const previous = history.length >= 2 ? history[history.length - 2] : undefined;

  return (
    <div className="page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(datasetSchema) }}
      />
      <h1 className="sr-only">How Philly feels about the Phillies, today.</h1>
      <Header today={today} />
      <Hero today={today} />

      <section className="section">
        <div className="section-head">
          <span className="section-num">01 · Trend</span>
          <h2 className="section-title">The last 30 days</h2>
        </div>
        <Trend history={history} todayScore={today.display_score} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">02 · The vibe</span>
          <h2 className="section-title">How Philly feels about the Phillies, today</h2>
        </div>
        <p className="editor-body">{today.vibe_summary ?? firstSentence(today.reasoning)}</p>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">03 · The count</span>
          <h2 className="section-title">The scoring dimensions</h2>
        </div>
        <Dimensions
          dimensions={today.dimensions}
          confidence={today.dimension_confidence}
          previousDimensions={previous?.dimensions}
        />
      </section>

      <HomeAskSection />

      <section className="section">
        <div className="section-head">
          <span className="section-num">05 · Cheers &amp; groans</span>
          <h2 className="section-title">What&apos;s working and what&apos;s not</h2>
        </div>
        <Themes themes={today.themes} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">06 · In the air</span>
          <h2 className="section-title">Hot takes from fans, journalists, and loudmouths</h2>
          <div className="section-sub">*As read by Phan-o-meter</div>
        </div>
        <Quotes today={today} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">07 · At the gate</span>
          <h2 className="section-title">Attendance</h2>
        </div>
        <Attendance att={today.hard_signals?.attendance} />
      </section>

      <Footer generatedAt={today.generated_at} />
    </div>
  );
}
