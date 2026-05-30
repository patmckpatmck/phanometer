import type { DailyReport, Quote, Voice, VoiceKey } from '@/lib/types';
import { VOICE_META } from '@/lib/format';

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
  if (id === 'youtube_fan') return 'Fan comments';
  if (id === 'twitter_fan') return 'Fan posts';
  return 'Talk radio';
}

interface VoiceLineProps {
  id: VoiceKey;
  data: Voice;
  asSummary?: boolean;
}

function hasSignal(data: Voice): boolean {
  return data != null && data.score != null;
}

function VoiceLine({ id, data, asSummary = false }: VoiceLineProps) {
  if (!hasSignal(data)) return null;
  const meta = VOICE_META[id];
  const byline = meta.pub ? `${meta.name}, ${meta.pub}` : meta.name;

  if (id === 'reddit' && asSummary) {
    return (
      <div className="pullquote reddit-style">
        <span className="pullquote-voice-tag tag-reddit">R/PHILLIES · AGGREGATE</span>
        <div className="pullquote-text red-text">{data.note}</div>
        <div className="pullquote-source">
          <span>r/phillies, aggregate read</span>
          <span className="pullquote-voice-score">score {data.score}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="pullquote black-style">
      <div className="pullquote-byline">{byline}</div>
      <div className="pullquote-text black-text">{data.note}</div>
      <div className="pullquote-source">
        <span>{voiceLabel(id)}</span>
        <span className="pullquote-voice-score">score {data.score}</span>
      </div>
    </div>
  );
}

const VOICE_ORDER: VoiceKey[] = ['reddit', 'beat_writer', 'fan_analyst', 'radio_populist', 'youtube_fan', 'twitter_fan'];

export function Quotes({ today }: { today: DailyReport }) {
  const activeVoices = VOICE_ORDER.filter(
    (v) => v !== 'reddit' && hasSignal(today.voice_breakdown[v]),
  );
  return (
    <div className="quotes-list">
      {hasSignal(today.voice_breakdown.reddit) && (
        <VoiceLine id="reddit" data={today.voice_breakdown.reddit} asSummary />
      )}
      {today.quotes.map((q, i) => (
        <QuoteCard key={`q${i}`} q={q} />
      ))}
      {activeVoices.map((v) => (
        <VoiceLine key={`v${v}`} id={v} data={today.voice_breakdown[v]} />
      ))}
    </div>
  );
}
