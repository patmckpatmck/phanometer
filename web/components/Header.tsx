import Link from 'next/link';
import { formatDate } from '@/lib/format';
import type { DailyReport } from '@/lib/types';
import { MastheadAskLink } from './MastheadAskLink';

const INSTAGRAM_ENABLED = true;

export function Header({
  today,
  metaLines,
}: {
  today: DailyReport;
  /** Overrides the default tagline + date lines (used by the offseason homepage). */
  metaLines?: [string, string];
}) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <Link href="/" className="topbar-mark-link" aria-label="Phanometer home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="topbar-mark" src="/assets/wordmark.png" alt="Phanometer" />
        </Link>
        <div className="topbar-meta">
          <div>{metaLines ? metaLines[0] : 'How Philly feels about the Phillies, today'}</div>
          <div>{metaLines ? metaLines[1].toUpperCase() : formatDate(today.date).toUpperCase()}</div>
        </div>
      </div>
      <div className="topbar-right">
        {INSTAGRAM_ENABLED ? (
          <a
            href="https://instagram.com/phanometer"
            target="_blank"
            rel="noopener noreferrer"
          >
            @phanometer
          </a>
        ) : (
          '@phanometer'
        )}
        <MastheadAskLink />
      </div>
    </header>
  );
}
