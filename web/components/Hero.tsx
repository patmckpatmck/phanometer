import { BellMeter } from './BellMeter';
import { bandFor } from '@/lib/moodBands';
import type { DailyReport } from '@/lib/types';

export function Hero({ today }: { today: DailyReport }) {
  const band = bandFor(today.display_score);
  const delta =
    today.baseline_score != null ? today.display_score - today.baseline_score : null;

  return (
    <div className="hero">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="hero-wordmark" src="/assets/wordmark.png" alt="Phanometer" />
      <BellMeter score={today.display_score} />
      <div className="readout">
        <div className="score">{today.display_score}</div>
        <div className={`mood mood-${band.slug}`}>{band.label}</div>
        <div className="readout-delta">
          {delta != null ? (
            <>
              {delta >= 0 ? (
                <span className="up">▲ {delta} PTS</span>
              ) : (
                <span className="down">▼ {Math.abs(delta)} PTS</span>
              )}{' '}
              VS. 30-DAY BASELINE ({today.baseline_score})
            </>
          ) : (
            <span>NO BASELINE YET — CALIBRATING</span>
          )}
        </div>
      </div>
    </div>
  );
}
