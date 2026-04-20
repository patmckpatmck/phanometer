import type { DailyReport, Quote, Voice, VoiceKey } from '@/lib/types';
import { VOICE_META } from '@/lib/format';

// Flip to true to re-render the r/phillies voice block once Reddit is back in
// the nightly pipeline (see .github/workflows/daily.yml, --no-reddit flag).
const REDDIT_ENABLED = false;

function isRedditSource(hint: string | undefined): boolean {
  return /reddit|r\/phillies/i.test(hint ?? '');
}

function QuoteCard({ q }: { q: Quote }) {
  if (isRedditSource(q.source_hint)) {
    return (
      <div className="pullquote reddit-style">
        <span className="pullquote-voice-tag tag-reddit">R/PHILLIES</span>
        <div className="pullquote-text red-text">{q.text}</div>
        <div className="pullquote-source">
          <span>{q.source_hint}</span>
          <span className="pullquote-voice-score">score {q.score}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="pullquote black-style">
      <div className="pullquote-byline">{q.source_hint}</div>
      <div className="pullquote-text black-text">{q.text}</div>
      <div className="pullquote-source">
        <span>Podcast</span>
        <span className="pullquote-voice-score">score {q.score}</span>
      </div>
    </div>
  );
}

function voiceLabel(id: VoiceKey): string {
  if (id === 'beat_writer') return 'Beat writer';
  if (id === 'fan_analyst') return 'Fan analyst';
  return 'Talk radio';
}

interface VoiceLineProps {
  id: VoiceKey;
  data: Voice;
  asSummary?: boolean;
}

function VoiceLine({ id, data, asSummary = false }: VoiceLineProps) {
  const meta = VOICE_META[id];
  const quiet = data == null || data.score == null;
  const byline = meta.pub ? `${meta.name}, ${meta.pub}` : meta.name;

  if (id === 'reddit' && asSummary) {
    return (
      <div className="pullquote reddit-style">
        <span className="pullquote-voice-tag tag-reddit">R/PHILLIES · AGGREGATE</span>
        {quiet ? (
          <>
            <div className="pullquote-text red-text quiet-text">
              Quiet today — thin thread activity.
            </div>
            <div className="pullquote-source">
              <span>Voice will return when a fresh signal lands.</span>
            </div>
          </>
        ) : (
          <>
            <div className="pullquote-text red-text">{data.note}</div>
            <div className="pullquote-source">
              <span>r/phillies, aggregate read</span>
              <span className="pullquote-voice-score">score {data.score}</span>
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="pullquote black-style">
      {quiet ? (
        <>
          <div className="pullquote-byline">{byline}</div>
          <div className="pullquote-text black-text quiet-text">
            Quiet today — no episode, no segment, or too thin to score.
          </div>
          <div className="pullquote-source">
            <span>Voice will return when a fresh signal lands.</span>
          </div>
        </>
      ) : (
        <>
          <div className="pullquote-byline">{byline}</div>
          <div className="pullquote-text black-text">{data.note}</div>
          <div className="pullquote-source">
            <span>{voiceLabel(id)}</span>
            <span className="pullquote-voice-score">score {data.score}</span>
          </div>
        </>
      )}
    </div>
  );
}

const VOICE_ORDER: VoiceKey[] = ['reddit', 'beat_writer', 'fan_analyst', 'radio_populist'];

export function Quotes({ today }: { today: DailyReport }) {
  const quotes = REDDIT_ENABLED
    ? today.quotes
    : today.quotes.filter((q) => !isRedditSource(q.source_hint));
  return (
    <div className="quotes-list">
      {REDDIT_ENABLED && (
        <VoiceLine id="reddit" data={today.voice_breakdown.reddit} asSummary />
      )}
      {quotes.map((q, i) => (
        <QuoteCard key={`q${i}`} q={q} />
      ))}
      {VOICE_ORDER.filter((v) => v !== 'reddit').map((v) => (
        <VoiceLine key={`v${v}`} id={v} data={today.voice_breakdown[v]} />
      ))}
    </div>
  );
}
