import type { DailyReport } from '@/lib/types';

// Offseason, full-season view of the meter. Unlike <Trend>, which lays days
// out at a fixed pixel pitch inside a horizontal scroller, this chart fits the
// whole season to the container width so it reads at a glance on any screen.
// Server component: no scroll position to manage, so no client JS needed.

export interface SeasonMarker {
  date: string;
  score: number;
  label: string;
  /** Where the label sits relative to its dot. */
  place: 'above' | 'below' | 'end';
}

interface Props {
  history: DailyReport[];
  markers: SeasonMarker[];
}

const BANDS = [
  { from: 70, to: 100, fill: '#0a2351', op: 0.06 },
  { from: 50, to: 70, fill: '#0a2351', op: 0.03 },
  { from: 30, to: 50, fill: '#c1121f', op: 0.03 },
  { from: 0, to: 30, fill: '#c1121f', op: 0.07 },
] as const;

// Whole days since epoch for an ISO date. X is positioned by calendar date,
// not array index, so missing days (runner outages) show their real spacing.
function dayNum(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
}

export function SeasonTrend({ history, markers }: Props) {
  const W = 1000;
  const H = 400;
  const start = dayNum(history[0].date);
  const end = dayNum(history[history.length - 1].date);
  const span = Math.max(1, end - start);
  const xPct = (iso: string): number => ((dayNum(iso) - start) / span) * 100;
  const x = (iso: string): number => (xPct(iso) / 100) * W;
  const y = (v: number): number => (1 - v / 100) * H;

  // Break the line on null-score days rather than interpolating through them.
  const segments: string[] = [];
  let seg: string[] = [];
  for (const d of history) {
    if (d.display_score == null) {
      if (seg.length) segments.push(seg.join(' '));
      seg = [];
      continue;
    }
    seg.push(`${seg.length ? 'L' : 'M'} ${x(d.date)} ${y(d.display_score)}`);
  }
  if (seg.length) segments.push(seg.join(' '));

  // One tick at the first of each month inside the season window.
  const ticks: { label: string; left: number }[] = [];
  const first = new Date(history[0].date + 'T12:00:00');
  const cursor = new Date(first.getFullYear(), first.getMonth() + 1, 1, 12);
  const last = new Date(history[history.length - 1].date + 'T12:00:00');
  while (cursor <= last) {
    const iso = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}-01`;
    ticks.push({
      label: cursor.toLocaleDateString('en-US', { month: 'short' }).toUpperCase(),
      left: xPct(iso),
    });
    cursor.setMonth(cursor.getMonth() + 1);
  }

  return (
    <div className="season-trend">
      <div className="season-frame">
        <div className="season-y">
          {[100, 75, 50, 25, 0].map((v) => (
            <div key={v} style={{ top: `${(1 - v / 100) * 100}%` }}>
              {v}
            </div>
          ))}
        </div>
        <div className="season-plot">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="season-svg"
            role="img"
            aria-label="Daily Phan-o-meter score across the 2026 season"
          >
            {BANDS.map((b, i) => (
              <rect
                key={i}
                x={0}
                y={y(b.to)}
                width={W}
                height={y(b.from) - y(b.to)}
                fill={b.fill}
                opacity={b.op}
              />
            ))}
            {[0, 25, 50, 75, 100].map((v) => (
              <line
                key={v}
                x1={0}
                x2={W}
                y1={y(v)}
                y2={y(v)}
                stroke="#14110f"
                strokeOpacity={v === 50 ? 0.35 : 0.15}
                strokeDasharray={v === 50 ? '0' : '3 3'}
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {ticks.map((t) => (
              <line
                key={t.label}
                x1={(t.left / 100) * W}
                x2={(t.left / 100) * W}
                y1={0}
                y2={H}
                stroke="#14110f"
                strokeOpacity={0.12}
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {segments.map((d, i) => (
              <path
                key={i}
                d={d}
                fill="none"
                stroke="#14110f"
                strokeWidth="2.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </svg>
          {/* Dots and labels are HTML so they stay round and crisp while the
              SVG stretches to the container. */}
          {markers.map((m) => (
            <div
              key={m.date + m.place}
              className={`season-marker season-marker--${m.place}`}
              style={{ left: `${xPct(m.date)}%`, top: `${100 - m.score}%` }}
            >
              <span className="season-marker-dot" />
              <span className="season-marker-label">{m.label}</span>
            </div>
          ))}
          <div className="season-x">
            {ticks.map((t) => (
              <div key={t.label} className="season-x-tick" style={{ left: `${t.left}%` }}>
                {t.label}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
