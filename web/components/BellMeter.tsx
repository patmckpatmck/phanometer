'use client';

import { useEffect, useState } from 'react';

interface Props {
  score: number;
  muted?: boolean;
}

// Arc geometry (SVG coords, viewBox 1000×560):
//   arc center (500, 180), radius 340, sweep ±90° from vertical-down
//   score 0   → needle at LEFT rim    (clapper swings LEFT,  POSITIVE CSS rotate)
//   score 50  → needle at bottom      (clapper hangs plumb,  rotate 0°)
//   score 100 → needle at RIGHT rim   (clapper swings RIGHT, NEGATIVE CSS rotate)
// In screen coords (y-down), CSS rotate(+θ) is CW on-screen, which tilts a
// downward-hanging clapper to the viewer's LEFT — that's the sign flip.

const SWEEP_HALF = 90;
// Bell's effective visual pivot in SVG coord space. X=500 is horizontal
// center. Y=90 is tuned empirically so the rotated clapper and the red needle
// point at the same arc tick; the bell image's transform-origin box measures
// ~98 but the PNG's visual clapper axis sits a few units lower.
const PIVOT_X = 500;
const PIVOT_Y = 90;
const ARC_CX = 500;
const ARC_CY = 180;
const ARC_R = 340;

function computeTargetAngle(score: number): number {
  const needleAngle = ((score - 50) / 50) * SWEEP_HALF;
  const rad = (needleAngle * Math.PI) / 180;
  const needleX = ARC_CX + ARC_R * Math.sin(rad);
  const needleY = ARC_CY + ARC_R * Math.cos(rad);
  const dx = needleX - PIVOT_X;
  const dy = needleY - PIVOT_Y;
  return -((Math.atan2(dx, dy) * 180) / Math.PI);
}

export function useBellAngle(score: number): number {
  const targetAngle = computeTargetAngle(score);
  // -100° puts the bell swung past the RIGHT (see sign convention above).
  // This is only visible pre-hydration; the effect overwrites on first rAF tick.
  const [angle, setAngle] = useState<number>(-SWEEP_HALF - 10);

  useEffect(() => {
    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion) {
      setAngle(targetAngle);
      return;
    }

    const start = performance.now();
    const initial = -Math.sign(targetAngle || 1) * (Math.abs(targetAngle) * 0.5 + 30);
    const final = targetAngle;

    const duration = 2600;
    const freq = 2.8;
    const damping = 4.0;

    let rafId = 0;

    const tick = (now: number): void => {
      const t = Math.min(1, (now - start) / duration);
      const osc = Math.cos(freq * Math.PI * t) * Math.exp(-damping * t);
      const ease = 1 - osc * (1 - t);
      const current = initial + (final - initial) * ease;

      if (t < 1) {
        setAngle(current);
        rafId = requestAnimationFrame(tick);
      } else {
        setAngle(final);
      }
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [targetAngle]);

  return angle;
}

interface Tick {
  s: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  major: boolean;
  medium: boolean;
  labelX: number;
  labelY: number;
}

// Round to 2 decimals: viewBox is 1000 units, so 0.01 is sub-pixel even on
// 4K displays, and the rounding eliminates server/client FP drift at the
// 15th digit that otherwise trips React hydration on SVG coord attributes.
const round2 = (n: number): number => Math.round(n * 100) / 100;

function buildTicks(): Tick[] {
  const cx = ARC_CX;
  const cy = ARC_CY;
  const r = ARC_R;

  const pt = (a: number, radius: number): [number, number] => {
    const rad = (a * Math.PI) / 180;
    return [round2(cx + radius * Math.sin(rad)), round2(cy + radius * Math.cos(rad))];
  };

  const ticks: Tick[] = [];
  for (let s = 0; s <= 100; s += 1) {
    const a = ((s - 50) / 50) * SWEEP_HALF;
    const major = s % 10 === 0;
    const medium = s % 5 === 0;
    const [x1, y1] = pt(a, r);
    const inner = major ? r - 22 : medium ? r - 14 : r - 9;
    const [x2, y2] = pt(a, inner);
    const [labelX, labelY] = pt(a, r + 30);
    ticks.push({ s, x1, y1, x2, y2, major, medium, labelX, labelY });
  }
  return ticks;
}

export function BellMeter({ score, muted = false }: Props) {
  const angle = useBellAngle(score);
  const ticks = buildTicks();

  const needleAngle = ((score - 50) / 50) * SWEEP_HALF;
  const rad = (needleAngle * Math.PI) / 180;
  const nx = round2(ARC_CX + (ARC_R - 34) * Math.sin(rad));
  const ny = round2(ARC_CY + (ARC_R - 34) * Math.cos(rad));
  const ntx = round2(ARC_CX + (ARC_R - 12) * Math.sin(rad));
  const nty = round2(ARC_CY + (ARC_R - 12) * Math.cos(rad));
  const perpX = Math.cos(rad);
  const perpY = -Math.sin(rad);
  const baseW = 10;
  const b1x = round2(nx + perpX * baseW);
  const b1y = round2(ny + perpY * baseW);
  const b2x = round2(nx - perpX * baseW);
  const b2y = round2(ny - perpY * baseW);

  return (
    <div className={muted ? 'meter-assembly meter-assembly--muted' : 'meter-assembly'}>
      <div className="bell-holder">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          className="bell-img"
          src="/assets/bell.png"
          alt="Liberty Bell"
          style={{ transform: `rotate(${angle.toFixed(2)}deg)` }}
        />
      </div>

      <svg className="meter-svg" viewBox="0 0 1000 560">
        {ticks.map((t) => (
          <line
            key={t.s}
            x1={t.x1}
            y1={t.y1}
            x2={t.x2}
            y2={t.y2}
            stroke="#14110f"
            strokeWidth={t.major ? 2.4 : t.medium ? 1.2 : 0.8}
            opacity={t.major ? 1 : t.medium ? 0.55 : 0.28}
            strokeLinecap="round"
          />
        ))}
        {ticks
          .filter((t) => t.major)
          .map((t) => (
            <text
              key={`L${t.s}`}
              x={t.labelX}
              y={t.labelY + 6}
              fontSize="22"
              fontFamily="var(--font-roboto-slab), 'Roboto Slab', serif"
              fill="#14110f"
              textAnchor="middle"
              fontWeight="600"
            >
              {t.s}
            </text>
          ))}
        <polygon points={`${ntx},${nty} ${b1x},${b1y} ${b2x},${b2y}`} fill="#c1121f" />
      </svg>
    </div>
  );
}
