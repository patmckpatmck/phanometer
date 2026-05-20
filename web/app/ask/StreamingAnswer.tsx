'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { AskActions } from '@/components/ask/AskActions';
import { AskAnswer } from '@/components/ask/AskAnswer';
import { AskExamples } from '@/components/ask/AskExamples';
import { AskInput } from '@/components/ask/AskInput';
import { AskQuestion } from '@/components/ask/AskQuestion';
import { AskSignature } from '@/components/ask/AskSignature';
import { AskStatusLine } from '@/components/ask/AskStatusLine';
import { slugify } from '@/lib/ask';

interface StreamingAnswerProps {
  examples: readonly string[];
}

type Phase = 'idle' | 'waiting' | 'streaming' | 'complete' | 'error';

/**
 * Client-side controller for /ask. Reads ?q= from URL (via useSearchParams,
 * required under `output: 'export'`) and either renders the empty state or
 * kicks off streaming.
 */
export function StreamingAnswer({ examples }: StreamingAnswerProps) {
  const searchParams = useSearchParams();
  const question = searchParams.get('q')?.trim() ?? '';

  if (!question) {
    return (
      <>
        <span className="section-num">04 · Ask the crowd</span>
        <h2 className="section-title">
          One question.
          <br />
          One answer.
        </h2>
        <p
          style={{
            fontFamily: 'var(--f-slab)',
            fontSize: 18,
            color: 'var(--ink-soft)',
            maxWidth: '44ch',
            margin: '0 0 26px',
            lineHeight: 1.5,
          }}
        >
          Ask the bot about how the mood has shifted this season. Phan-o-meter will give
          you a straight answer based on all the grumbling it&apos;s heard.
        </p>
        <AskInput placeholder="What do you want to know?" />
        <AskExamples header="Some places to start" examples={examples} />
      </>
    );
  }

  // Remount on question change so the streaming effect re-fires cleanly.
  return <AnsweringFlow key={question} question={question} />;
}

/**
 * The actual fetch/stream/render flow, isolated so React unmounts and
 * remounts it on question change (effect re-runs cleanly).
 */
function AnsweringFlow({ question }: { question: string }) {
  // `phase` drives which subcomponents render. `attempt` lets the Retry
  // button force-rerun the same query by changing the effect key.
  const [phase, setPhase] = useState<Phase>('waiting');
  const [elapsed, setElapsed] = useState('0.0s');
  const [answerText, setAnswerText] = useState('');
  const [statusFading, setStatusFading] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // Accumulator ref — receives every decoded chunk synchronously. The state
  // update is throttled via rAF so React doesn't reconcile per-token.
  const accumulatedRef = useRef('');
  const rafScheduledRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const abortController = new AbortController();
    const startedAt = Date.now();
    accumulatedRef.current = '';
    setAnswerText('');
    setStatusFading(false);
    setPhase('waiting');

    // Elapsed counter ticks every 100ms until first token arrives.
    const elapsedInterval = window.setInterval(() => {
      if (cancelled) return;
      const secs = (Date.now() - startedAt) / 1000;
      setElapsed(`${secs.toFixed(1)}s`);
    }, 100);

    function scheduleRender() {
      if (rafScheduledRef.current) return;
      rafScheduledRef.current = true;
      window.requestAnimationFrame(() => {
        rafScheduledRef.current = false;
        if (cancelled) return;
        setAnswerText(accumulatedRef.current);
      });
    }

    async function run() {
      try {
        const response = await fetch('/api/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let firstChunk = true;

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          if (cancelled) {
            reader.cancel().catch(() => {});
            return;
          }
          const text = decoder.decode(value, { stream: true });
          if (!text) continue;

          accumulatedRef.current += text;

          if (firstChunk) {
            firstChunk = false;
            window.clearInterval(elapsedInterval);
            // Fade out status line (200ms) then transition to streaming phase.
            setStatusFading(true);
            window.setTimeout(() => {
              if (cancelled) return;
              setPhase('streaming');
            }, 200);
          }

          scheduleRender();
        }

        // Drain decoder of any trailing bytes.
        const tail = decoder.decode();
        if (tail) {
          accumulatedRef.current += tail;
          scheduleRender();
        }

        if (cancelled) return;
        // Force one final state sync in case the last rAF hadn't fired.
        setAnswerText(accumulatedRef.current);
        setPhase('complete');
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.name === 'AbortError') return;
        window.clearInterval(elapsedInterval);
        setPhase('error');
      }
    }

    run();

    return () => {
      cancelled = true;
      window.clearInterval(elapsedInterval);
      abortController.abort();
    };
    // Re-run when the question changes or the user clicks Retry (attempt++).
  }, [question, attempt]);

  return (
    <>
      <AskQuestion question={question} />

      {phase === 'waiting' ? (
        <AskStatusLine elapsed={elapsed} fading={statusFading} />
      ) : null}

      {phase === 'streaming' || phase === 'complete' ? (
        <AskAnswer text={answerText} streaming={phase === 'streaming'} />
      ) : null}

      {phase === 'streaming' ? (
        <div className="ask-meta-row is-streaming" aria-live="polite">
          <span>Answering · streaming</span>
          <span>—</span>
        </div>
      ) : null}

      {phase === 'error' ? (
        <ErrorBlock onRetry={() => setAttempt((n) => n + 1)} />
      ) : null}

      {phase === 'complete' ? (
        <>
          <AskSignature slug={slugify(question)} />
          <AskActions />
        </>
      ) : null}
    </>
  );
}

function ErrorBlock({ onRetry }: { onRetry: () => void }) {
  return (
    <div style={{ marginTop: 12 }}>
      <p
        style={{
          fontFamily: 'var(--f-slab)',
          fontSize: 18,
          color: 'var(--ink)',
          margin: '0 0 14px',
        }}
      >
        Lost the line. Try again?
      </p>
      <button
        type="button"
        className="ask-submit"
        style={{ padding: '12px 22px', fontSize: 11 }}
        onClick={onRetry}
      >
        Retry →
      </button>
    </div>
  );
}
