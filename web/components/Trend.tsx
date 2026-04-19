'use client';

import { useEffect, useRef } from 'react';
import { formatDateShort } from '@/lib/format';
import type { DailyReport } from '@/lib/types';

interface Props {
  history: DailyReport[];
  todayScore: number;
}

const BANDS = [
  { from: 70, to: 100, fill: '#0a2351', op: 0.06 },
  { from: 50, to: 70, fill: '#0a2351', op: 0.03 },
  { from: 30, to: 50, fill: '#c1121f', op: 0.03 },
  { from: 0, to: 30, fill: '#c1121f', op: 0.07 },
] as const;

export function Trend({ history, todayScore }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, []);

  const days = history.length;

  if (days < 3) {
    const startDate = new Date();
    startDate.setDate(startDate.getDate() + (3 - days));
    return (
      <div className="trend-calibrating">
        Phan-o-meter is calibrating. Daily scores shown; 30-day trend begins{' '}
        {startDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric' })}.
      </div>
    );
  }

  const n = days;
  const H = 420;
  const PX_PER_DAY = 44;
  const W = Math.max(760, n * PX_PER_DAY);
  const x = (i: number): number => (i / Math.max(1, n - 1)) * W;
  const y = (v: number): number => (1 - v / 100) * H;

  const points = history.map((d, i) => [x(i), y(d.display_score)] as const);
  const pathD = points
    .map((p, i) => (i === 0 ? `M ${p[0]} ${p[1]}` : `L ${p[0]} ${p[1]}`))
    .join(' ');

  const baselinePoints = history
    .map((d, i) =>
      d.baseline_score != null ? ([x(i), y(d.baseline_score)] as const) : null,
    )
    .filter((p): p is readonly [number, number] => p !== null);
  const baselinePath = baselinePoints.length
    ? baselinePoints
        .map((p, i) => (i === 0 ? `M ${p[0]} ${p[1]}` : `L ${p[0]} ${p[1]}`))
        .join(' ')
    : null;

  const calibratingNote =
    days < 30 ? `${days} days in — fills in as history lengthens` : null;

  const todayX = x(n - 1);
  const todayY = y(todayScore);

  const dateTicks = history
    .map((d, i) => ({ i, date: d.date, x: x(i) }))
    .filter((_, i) => i === 0 || i === history.length - 1 || i % 5 === 0);

  return (
    <div className="trend-wrap">
      <div className="trend-frame">
        <div className="trend-y">
          {[100, 75, 50, 25, 0].map((v) => (
            <div key={v} style={{ top: `${(1 - v / 100) * 100}%` }}>
              {v}
            </div>
          ))}
        </div>
        <div className="trend-scroll" ref={scrollRef}>
          <div className="trend-plot" style={{ width: `${W}px` }}>
            <svg
              viewBox={`0 0 ${W} ${H}`}
              preserveAspectRatio="none"
              className="trend-svg"
              style={{ width: `${W}px`, height: '100%' }}
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
              {baselinePath && (
                <path
                  d={baselinePath}
                  fill="none"
                  stroke="#0a2351"
                  strokeWidth="2.5"
                  strokeDasharray="5 5"
                  opacity="0.75"
                  vectorEffect="non-scaling-stroke"
                />
              )}
              <path
                d={pathD}
                fill="none"
                stroke="#14110f"
                strokeWidth="3"
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
              {points.map((p, i) => (
                <circle key={i} cx={p[0]} cy={p[1]} r={3} fill="#14110f" />
              ))}
              <line
                x1={todayX}
                x2={todayX}
                y1={0}
                y2={H}
                stroke="#c1121f"
                strokeWidth="2"
                strokeDasharray="4 4"
                opacity="0.7"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={todayX}
                cy={todayY}
                r={10}
                fill="#c1121f"
                stroke="#f4ead8"
                strokeWidth="3"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <div className="trend-today-label" style={{ left: `${todayX}px` }}>
              TODAY
            </div>
            <div className="trend-x-inline">
              {dateTicks.map((t) => (
                <div key={t.i} className="trend-x-tick" style={{ left: `${t.x}px` }}>
                  {formatDateShort(t.date)}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="trend-scroll-hint">↔ swipe to scan the month</div>
      <div className="trend-legend">
        <span>
          <span className="sw" style={{ background: '#14110f' }} />
          Daily score
        </span>
        {baselinePath && (
          <span>
            <span
              className="sw"
              style={{ background: 'transparent', borderTop: '2px dashed #0a2351' }}
            />
            30-day baseline
          </span>
        )}
        <span>
          <span className="sw" style={{ background: '#c1121f' }} />
          Today
        </span>
        {calibratingNote && <span style={{ fontStyle: 'italic' }}>· {calibratingNote}</span>}
      </div>
    </div>
  );
}
