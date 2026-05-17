import { Suspense } from 'react';
import { Footer } from '@/components/Footer';
import { Header } from '@/components/Header';
import { readHistory } from '@/lib/data';
import { getCorpusStats, ASK_PAGE_EXAMPLES } from '@/lib/ask';
import { StreamingAnswer } from './StreamingAnswer';

/**
 * /ask — the column.
 *
 * Server component that loads the history at build time to derive the corpus
 * footnote stats (passed to the client) and to feed the existing Header /
 * Footer components with `today`. Under `output: 'export'`, the page itself
 * is statically generated; the actual ?q= read and streaming flow happen
 * client-side inside StreamingAnswer (via useSearchParams).
 */
export default async function AskPage() {
  const { history, today } = await readHistory();
  const corpus = getCorpusStats(history);

  return (
    <div className="page">
      <Header today={today} />
      <main className="ask-column" style={{ paddingTop: 30 }}>
        <Suspense fallback={null}>
          <StreamingAnswer corpus={corpus} examples={ASK_PAGE_EXAMPLES} />
        </Suspense>
      </main>
      <Footer generatedAt={today.generated_at} />
    </div>
  );
}
