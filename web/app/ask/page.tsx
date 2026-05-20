import { Suspense } from 'react';
import type { Metadata } from 'next';
import { Footer } from '@/components/Footer';
import { Header } from '@/components/Header';
import { readHistory } from '@/lib/data';
import { ASK_PAGE_EXAMPLES } from '@/lib/ask';
import { StreamingAnswer } from './StreamingAnswer';

const ASK_TITLE = 'Ask Phan-o-meter — Phillies fan-mood Q&A';
const ASK_DESCRIPTION =
  'One question, one answer. Phan-o-meter answers Phillies fan-mood questions grounded in every day of recorded sentiment.';

export const metadata: Metadata = {
  title: { absolute: ASK_TITLE },
  description: ASK_DESCRIPTION,
  alternates: { canonical: '/ask' },
  openGraph: {
    title: ASK_TITLE,
    description: ASK_DESCRIPTION,
    url: 'https://www.phanometer.com/ask',
    images: [
      {
        url: '/assets/og-default.png',
        width: 1200,
        height: 630,
        alt: ASK_TITLE,
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: ASK_TITLE,
    description: ASK_DESCRIPTION,
    images: ['/assets/og-default.png'],
  },
};

/**
 * /ask — the column.
 *
 * Server component that loads today's report to feed the existing Header /
 * Footer components. Under `output: 'export'`, the page itself is statically
 * generated; the actual ?q= read and streaming flow happen client-side inside
 * StreamingAnswer (via useSearchParams).
 */
export default async function AskPage() {
  const { today } = await readHistory();

  return (
    <div className="page">
      <h1 className="sr-only">Ask Phan-o-meter</h1>
      <Header today={today} />
      <main className="ask-column" style={{ paddingTop: 30 }}>
        <Suspense fallback={null}>
          <StreamingAnswer examples={ASK_PAGE_EXAMPLES} />
        </Suspense>
      </main>
      <Footer generatedAt={today.generated_at} />
    </div>
  );
}