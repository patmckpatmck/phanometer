interface AskQuestionProps {
  question: string;
}

export function AskQuestion({ question }: AskQuestionProps) {
  return (
    <>
      <span className="ask-eyebrow">The question</span>
      <h2 className="ask-q">{question}</h2>
    </>
  );
}
