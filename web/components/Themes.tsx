import type { Theme } from '@/lib/types';

export function Themes({ themes }: { themes: Theme[] }) {
  return (
    <div className="themes-row">
      {themes.slice(0, 5).map((t, i) => {
        const sign = t.delta > 0 ? '+' : '';
        const cls = t.delta < 0 ? 'delta-neg' : t.delta > 0 ? 'delta-pos' : 'delta-zero';
        return (
          <div className="theme" key={i}>
            <div className={`theme-delta ${cls}`}>
              {sign}
              {t.delta}
            </div>
            <div className="theme-name">{t.name}</div>
            <div className="theme-sample">{t.sample}</div>
          </div>
        );
      })}
      <div className="theme theme-empty" aria-hidden="true" />
    </div>
  );
}
