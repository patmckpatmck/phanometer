'use client';

import { useEffect, useRef } from 'react';
import { formatDateShort } from '@/lib/format';
import type { DailyReport } from '@/lib/types';

interface Props {
  history: DailyReport[];
  todayScore: number | null;
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

  if (days < 30) {
    const anchor = history[0]?.date;
    const start = anchor ? new Date(anchor + 'T12:00:00') : new Date();
    start.setDate(start.getDate() + 30);
    const publishDate = start.toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
    return (
      <div className="trend-calibrating">
        <p className="trend-calibrating-body">
          Phan-o-meter is calibrating. The first 30-day trend publishes{' '}
          {publishDate}. Until then, today&rsquo;s score stands alone.
        </p>
      </div>
    );
  }

  const n = days;
  const H = 420;
  const PX_PER_DAY = 44;
  const W = Math.max(760, n * PX_PER_DAY);
  const x = (i: number): number => (i / Math.max(1, n - 1)) * W;
  const y = (v: number): number => (1 - v / 100) * H;

  // Build per-day points only where display_score is present. Split the path
  // into separate segments across gaps so null days render as breaks in the
  // line, not interpolated through.
  const dots = history
    .map((d, i) =>
      d.display_score != null
        ? ({ cx: x(i), cy: y(d.display_score) } as const)
        : null,
    )
    .filter((p): p is { readonly cx: number; readonly cy: number } => p !== null);

  const pathSegments: string[] = [];
  let currentSeg: string[] = [];
  history.forEach((d, i) => {
    if (d.display_score == null) {
      if (currentSeg.length) {
        pathSegments.push(currentSeg.join(' '));
        currentSeg = [];
      }
      return;
    }
    const cmd = currentSeg.length === 0 ? 'M' : 'L';
    currentSeg.push(`${cmd} ${x(i)} ${y(d.display_score)}`);
  });
  if (currentSeg.length) pathSegments.push(currentSeg.join(' '));

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

  const todayX = x(n - 1);
  const todayY = todayScore != null ? y(todayScore) : null;

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
              {pathSegments.map((d, i) => (
                <path
                  key={`seg${i}`}
                  d={d}
                  fill="none"
                  stroke="#14110f"
                  strokeWidth="3"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              {dots.map((p, i) => (
                <circle key={i} cx={p.cx} cy={p.cy} r={3} fill="#14110f" />
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
              {todayY != null && (
                <circle
                  cx={todayX}
                  cy={todayY}
                  r={10}
                  fill="#c1121f"
                  stroke="#f4ead8"
                  strokeWidth="3"
                  vectorEffect="non-scaling-stroke"
                />
              )}
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
      </div>
    </div>
  );
}
