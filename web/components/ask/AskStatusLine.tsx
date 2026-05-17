interface AskStatusLineProps {
  /** Elapsed seconds since request kicked off, formatted as e.g. "4.2s". */
  elapsed: string;
  /** When true, applies opacity transition before parent unmounts. */
  fading?: boolean;
}

export function AskStatusLine({ elapsed, fading = false }: AskStatusLineProps) {
  return (
    <div
      className={`ask-loading-row${fading ? ' is-fading' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="dot" aria-hidden />
      <span className="label">Reading the room</span>
      <span className="elapsed">· {elapsed}</span>
    </div>
  );
}
