import Link from 'next/link';
import { formatDateShort } from '@/lib/format';
import type { DailyReport } from '@/lib/types';

interface Props {
  history: DailyReport[];
  currentIndex: number;
}

/**
 * Prev / next navigation between adjacent daily archives. Rendered both at
 * the top and bottom of an archive page since readers commonly scan multiple
 * days in sequence.
 *
 * When the current entry is the latest in history (the day shown on the
 * homepage), the "next" slot links to / labeled "Today →" as a clearer
 * escape hatch back to the live readout.
 */
export function DayNav({ history, currentIndex }: Props) {
  const prev = currentIndex > 0 ? history[currentIndex - 1] : null;
  const next =
    currentIndex < history.length - 1 ? history[currentIndex + 1] : null;
  const isLatest = currentIndex === history.length - 1;

  return (
    <nav className="day-nav" aria-label="Daily archive navigation">
      <div className="day-nav-side day-nav-prev">
        {prev ? (
          <Link href={`/day/${prev.date}`}>
            <span aria-hidden="true">← </span>
            {formatDateShort(prev.date)}
          </Link>
        ) : null}
      </div>
      <div className="day-nav-side day-nav-next">
        {next ? (
          <Link href={`/day/${next.date}`}>
            {formatDateShort(next.date)}
            <span aria-hidden="true"> →</span>
          </Link>
        ) : isLatest ? (
          <Link href="/">
            Today
            <span aria-hidden="true"> →</span>
          </Link>
        ) : null}
      </div>
    </nav>
  );
}
