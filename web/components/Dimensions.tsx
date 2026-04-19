import type { DimensionConfidence, Dimensions as DimsType } from '@/lib/types';
import { DIM_LABELS, DIMENSION_ORDER } from '@/lib/format';

interface Props {
  dimensions: DimsType;
  confidence: DimensionConfidence;
}

export function Dimensions({ dimensions, confidence }: Props) {
  const values = DIMENSION_ORDER.map((k) => dimensions[k]).filter(
    (v): v is number => v != null,
  );
  const mean = values.reduce((a, b) => a + b, 0) / Math.max(1, values.length);
  const std = Math.sqrt(
    values.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, values.length),
  );

  const rows = DIMENSION_ORDER.filter((k) => dimensions[k] != null).map((k) => {
    const score = dimensions[k];
    return {
      key: k,
      label: DIM_LABELS[k] ?? k,
      score,
      conf: confidence?.[k] ?? 50,
      divergent: Math.abs(score - mean) > std * 1.4 && std > 5,
    };
  });

  return (
    <div className="dims">
      <div className="dims-head">
        <div>Dimension</div>
        <div>Score</div>
        <div style={{ textAlign: 'right' }}>Score</div>
        <div style={{ textAlign: 'right' }}>Confidence</div>
      </div>
      {rows.map((r) => (
        <div className="dims-row" key={r.key}>
          <div className="dim-name">{r.label}</div>
          <div
            className={`dim-bar ${r.divergent ? 'divergent' : ''}`}
            style={{ opacity: 0.35 + (r.conf / 100) * 0.65 }}
          >
            <div className="dim-bar-fill" style={{ width: `${r.score}%` }} />
            <div className="dim-bar-ticks" />
          </div>
          <div className="dim-score">{r.score}</div>
          <div className="dim-conf">conf {r.conf}</div>
        </div>
      ))}
    </div>
  );
}
