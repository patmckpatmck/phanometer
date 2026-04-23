import { BellMeter } from './BellMeter';
import { bandFor } from '@/lib/moodBands';
import type { DailyReport } from '@/lib/types';

export function Hero({ today }: { today: DailyReport }) {
  // Treat either the explicit flag or a null display_score as insufficient —
  // old records (pre-insufficient_signal field) stay on the normal path.
  const insufficient =
    today.insufficient_signal === true || today.display_score == null;
  const score = today.display_score;
  const band = score != null ? bandFor(score) : null;
  const delta =
    !insufficient && score != null && today.baseline_score != null
      ? score - today.baseline_score
      : null;

  return (
    <div className="hero">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="hero-wordmark" src="/assets/wordmark.png" alt="Phanometer" />
      <BellMeter score={score ?? 50} muted={insufficient} />
      <div className="readout">
        {insufficient ? (
          <div className="insufficient insufficient-hero">
            Not enough signal today
          </div>
        ) : (
          <>
            <div className="score">{score}</div>
            {band && <div className={`mood mood-${band.slug}`}>{band.label}</div>}
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
          </>
        )}
      </div>
    </div>
  );
}
