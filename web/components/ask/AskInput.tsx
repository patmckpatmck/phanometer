'use client';

import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

interface AskInputProps {
  placeholder: string;
  /**
   * If provided, called with the question instead of navigating. Used by the
   * /ask empty state where StreamingAnswer handles the navigation+stream itself.
   */
  onSubmitQuestion?: (question: string) => void;
}

/**
 * The input + submit button used on both the homepage section and the /ask
 * empty state. Falls back to a native form GET to /ask?q=<text> when JS is
 * disabled. With JS, intercepts submit and either navigates client-side (for
 * the homepage entry surface) or delegates to onSubmitQuestion.
 */
export function AskInput({ placeholder, onSubmitQuestion }: AskInputProps) {
  const router = useRouter();
  const [value, setValue] = useState('');

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    // Only intercept when JS is loaded; the native form action="/ask" is the
    // no-JS fallback and works without this handler running at all.
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    if (onSubmitQuestion) {
      onSubmitQuestion(trimmed);
    } else {
      router.push(`/ask?q=${encodeURIComponent(trimmed)}`);
    }
  }

  return (
    <form className="ask-input-wrap" action="/ask" method="GET" onSubmit={handleSubmit}>
      <input
        className="ask-input"
        name="q"
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        autoComplete="off"
      />
      <button className="ask-submit" type="submit" disabled={value.trim().length === 0}>
        Ask →
      </button>
    </form>
  );
}
