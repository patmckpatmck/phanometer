'use client';

import { useEffect, useState, type CSSProperties } from 'react';

interface Props {
  score: number;
}

// Arc geometry (SVG coords, viewBox 1000×560):
//   arc center (500, 180), radius 340, sweep ±90° from vertical-down
//   score 0   → needle at LEFT rim    (clapper swings LEFT,  POSITIVE CSS rotate)
//   score 50  → needle at bottom      (clapper hangs plumb,  rotate 0°)
//   score 100 → needle at RIGHT rim   (clapper swings RIGHT, NEGATIVE CSS rotate)
// In screen coords (y-down), CSS rotate(+θ) is CW on-screen, which tilts a
// downward-hanging clapper to the viewer's LEFT — that's the sign flip.

const SWEEP_HALF = 90;
const PIVOT_X = 500;
const PIVOT_Y = 65;
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

interface BellAngleState {
  angle: number;
  idle: boolean;
}

export function useBellAngle(score: number): BellAngleState {
  const targetAngle = computeTargetAngle(score);
  // -100° puts the bell swung past the RIGHT (see sign convention above).
  // This is only visible pre-hydration; the effect overwrites on first rAF tick.
  const [state, setState] = useState<BellAngleState>({
    angle: -SWEEP_HALF - 10,
    idle: false,
  });

  useEffect(() => {
    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion) {
      setState({ angle: targetAngle, idle: false });
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
      const idleSway = Math.sin(now / 1700) * 0.8 * t;

      if (t < 1) {
        setState({ angle: current + idleSway, idle: false });
        rafId = requestAnimationFrame(tick);
      } else {
        setState({ angle: final, idle: true });
      }
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [targetAngle]);

  return state;
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

function buildTicks(): Tick[] {
  const cx = ARC_CX;
  const cy = ARC_CY;
  const r = ARC_R;

  // Round to 2 decimals: viewBox is 1000 units, so 0.01 is sub-pixel even on
  // 4K displays, and the rounding eliminates server/client FP drift at the
  // 15th digit that otherwise trips React hydration on these 101 ticks.
  const round2 = (n: number): number => Math.round(n * 100) / 100;

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

export function BellMeter({ score }: Props) {
  const { angle, idle } = useBellAngle(score);
  const ticks = buildTicks();

  const needleAngle = ((score - 50) / 50) * SWEEP_HALF;
  const rad = (needleAngle * Math.PI) / 180;
  const nx = ARC_CX + (ARC_R - 34) * Math.sin(rad);
  const ny = ARC_CY + (ARC_R - 34) * Math.cos(rad);
  const ntx = ARC_CX + (ARC_R - 12) * Math.sin(rad);
  const nty = ARC_CY + (ARC_R - 12) * Math.cos(rad);
  const perpX = Math.cos(rad);
  const perpY = -Math.sin(rad);
  const baseW = 10;
  const b1x = nx + perpX * baseW;
  const b1y = ny + perpY * baseW;
  const b2x = nx - perpX * baseW;
  const b2y = ny - perpY * baseW;

  const bellStyle: CSSProperties = idle
    ? ({ ['--bell-angle' as string]: `${angle.toFixed(2)}deg` } as CSSProperties)
    : { transform: `rotate(${angle.toFixed(2)}deg)` };

  return (
    <div className="meter-assembly">
      <div className="bell-holder">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          className={idle ? 'bell-img bell-idle' : 'bell-img'}
          src="/assets/bell.png"
          alt="Liberty Bell"
          style={bellStyle}
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
