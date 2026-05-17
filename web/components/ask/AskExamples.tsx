'use client';

import { useRouter } from 'next/navigation';

interface AskExamplesProps {
  header: string;
  examples: readonly string[];
  /**
   * Optional: if provided, clicking an example invokes this instead of
   * router-pushing to /ask?q=. Used by the /ask empty state.
   */
  onPick?: (question: string) => void;
}

/**
 * "For instance" / "Some places to start" list. Each row is a button so the
 * click is a real semantic action, no `<a>` href fakery. Clicking an example
 * is equivalent to typing that exact text into the input and submitting.
 */
export function AskExamples({ header, examples, onPick }: AskExamplesProps) {
  const router = useRouter();

  function pick(question: string) {
    if (onPick) onPick(question);
    else router.push(`/ask?q=${encodeURIComponent(question)}`);
  }

  return (
    <>
      <div className="ask-suggest-header">{header}</div>
      <ul className="ask-suggest-list">
        {examples.map((q) => (
          <li key={q}>
            <button
              type="button"
              className="ask-suggest-button"
              onClick={() => pick(q)}
            >
              <span>{q}</span>
              <span className="arrow">↗</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
