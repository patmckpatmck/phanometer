import { formatDate } from '@/lib/format';
import type { DailyReport } from '@/lib/types';

export function Header({ today }: { today: DailyReport }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="topbar-mark" src="/assets/wordmark.png" alt="Phanometer" />
        <div className="topbar-meta">
          <div>How Philly feels about the Phillies, today</div>
          <div>{formatDate(today.date).toUpperCase()}</div>
        </div>
      </div>
      <div className="topbar-right">@phanometer</div>
    </header>
  );
}
