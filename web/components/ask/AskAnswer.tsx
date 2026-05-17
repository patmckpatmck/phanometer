interface AskAnswerProps {
  /**
   * The accumulated stream text. Split on "\n\n" into separate <p> elements.
   * The trailing <p> hosts the streaming cursor when `streaming` is true.
   */
  text: string;
  streaming: boolean;
}

/**
 * Renders the streaming answer body. Parent component owns the text state and
 * passes the full accumulated string on each throttled update; this component
 * only does the paragraph split + cursor placement.
 */
export function AskAnswer({ text, streaming }: AskAnswerProps) {
  const paragraphs = text.length > 0 ? text.split(/\n\n+/) : [''];

  return (
    <div className="ask-answer">
      {paragraphs.map((para, i) => {
        const isLast = i === paragraphs.length - 1;
        return (
          <p key={i}>
            {para}
            {streaming && isLast ? <span className="cursor" aria-hidden /> : null}
          </p>
        );
      })}
    </div>
  );
}
