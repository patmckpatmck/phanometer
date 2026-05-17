import type { CorpusStats } from '@/lib/ask';

interface AskSignatureProps {
  corpus: CorpusStats;
  slug: string;
}

export function AskSignature({ corpus, slug }: AskSignatureProps) {
  return (
    <div className="ask-signature">
      <div className="em">— Phan-o-meter, reading from the daily record.</div>
      <div>
        Drawn from {corpus.podcastEpisodes} podcast episodes · {corpus.dailyReadings} daily
        readings · {corpus.dateFrom} – {corpus.dateTo}
      </div>
      <div style={{ marginTop: 8 }}>
        <span className="permalink">phanometer.com/ask/{slug}</span>
      </div>
    </div>
  );
}
