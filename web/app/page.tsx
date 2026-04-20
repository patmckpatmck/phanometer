import { readHistory } from '@/lib/data';
import { Attendance } from '@/components/Attendance';
import { Dimensions } from '@/components/Dimensions';
import { Footer } from '@/components/Footer';
import { Header } from '@/components/Header';
import { Hero } from '@/components/Hero';
import { Quotes } from '@/components/Quotes';
import { Themes } from '@/components/Themes';
import { Trend } from '@/components/Trend';

function firstSentence(text: string): string {
  const parts = text.match(/[^.!?]+[.!?]+(\s|$)/g);
  return (parts?.[0] ?? text).trim();
}

export default async function Page() {
  const { history, today } = await readHistory();
  const previous = history.length >= 2 ? history[history.length - 2] : undefined;

  return (
    <div className="page">
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
        <p className="editor-body">{firstSentence(today.reasoning)}</p>
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

      <section className="section">
        <div className="section-head">
          <span className="section-num">04 · Cheers &amp; groans</span>
          <h2 className="section-title">What&apos;s working and what&apos;s not</h2>
        </div>
        <Themes themes={today.themes} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">05 · In the air</span>
          <h2 className="section-title">Hot takes from fans, journalists, and loudmouths</h2>
          <div className="section-sub">*As read by Phan-o-meter</div>
        </div>
        <Quotes today={today} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="section-num">06 · At the gate</span>
          <h2 className="section-title">Attendance</h2>
        </div>
        <Attendance att={today.hard_signals?.attendance} />
      </section>

      <Footer generatedAt={today.generated_at} />
    </div>
  );
}
