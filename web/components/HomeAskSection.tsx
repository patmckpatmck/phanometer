import { AskExamples } from '@/components/ask/AskExamples';
import { AskInput } from '@/components/ask/AskInput';
import { HOMEPAGE_EXAMPLES } from '@/lib/ask';

export function HomeAskSection() {
  return (
    <section className="section">
      <div className="section-head">
        <span className="section-num">04 · Ask the crowd</span>
        <h2 className="section-title">
          One question.
          <br />
          One answer.
        </h2>
      </div>
      <p className="entry-sub">
        Ask the bot about how the mood has shifted this season. Phan-o-meter will give
        you a straight answer based on all the grumbling it&apos;s heard.
      </p>
      <AskInput placeholder="Ask away." />
      <AskExamples header="For instance" examples={HOMEPAGE_EXAMPLES} />
    </section>
  );
}
