import type { Attendance as AttType } from '@/lib/types';
import { isAttendanceOk } from '@/lib/types';
import { formatDateShort, teamCallsign } from '@/lib/format';

export function Attendance({ att }: { att: AttType | undefined }) {
  if (!isAttendanceOk(att)) {
    const window = att?.recent_window_days ?? 14;
    return (
      <div className="attendance">
        <div className="insufficient">
          Not enough home games in the last {window} days to establish a gate read. Returns once a
          baseline window is populated.
        </div>
      </div>
    );
  }

  const flagged = att.canary_signal;
  const delta = att.delta_pct;
  const sign = delta > 0 ? '+' : '';
  const deltaCls = delta < 0 ? 'down' : 'up';
  const sortedGames = [...att.recent_games].sort((a, b) => b.date.localeCompare(a.date));

  return (
    <div className={`attendance ${flagged ? 'flagged' : ''}`}>
      <div className="att-head">
        <div className="label">Recent gate, 14-day window</div>
        <div className="big">
          {att.recent_avg_pct.toFixed(1)}
          <span className="unit">%</span>
        </div>
        <div className="delta">
          <span className={deltaCls}>
            {sign}
            {delta.toFixed(1)}pp
          </span>{' '}
          <span style={{ color: 'var(--ink-mute)' }}>
            vs. {att.baseline_avg_pct.toFixed(1)}% baseline · {att.baseline_source}
          </span>
        </div>
        {flagged && <div className="att-flag">Fans are voting with their feet</div>}
        <div className="att-body">
          Sentiment is what people say; the gate is what they do. Capacity is{' '}
          {att.capacity.toLocaleString()} at Citizens Bank Park; the baseline compares against{' '}
          {att.baseline_games_count} games from last year&apos;s same calendar window.
        </div>
      </div>
      <div className="att-games">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Opponent</th>
              <th>Result</th>
              <th style={{ textAlign: 'right' }}>Attendance</th>
              <th style={{ textAlign: 'right' }}>% Cap.</th>
            </tr>
          </thead>
          <tbody>
            {sortedGames.map((g) => {
              const isW = g.result.startsWith('W');
              const pctColor =
                g.pct_capacity < 85
                  ? 'var(--red)'
                  : g.pct_capacity > 100
                    ? 'var(--navy)'
                    : 'var(--ink)';
              return (
                <tr key={g.game_pk}>
                  <td>
                    {formatDateShort(g.date)}{' '}
                    <span style={{ color: 'var(--ink-mute)' }}>
                      {g.day_of_week.slice(0, 3).toUpperCase()}
                    </span>
                  </td>
                  <td className="opp">vs. {teamCallsign(g.opponent)}</td>
                  <td className={isW ? 'result-w' : 'result-l'}>{g.result}</td>
                  <td className="pct">{g.attendance.toLocaleString()}</td>
                  <td className="pct" style={{ color: pctColor }}>
                    {g.pct_capacity.toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
