import { formatTime } from '@/lib/format';

export function Footer({ generatedAt }: { generatedAt: string }) {
  return (
    <footer className="footer">
      <div className="footer-brand">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="footer-mark" src="/assets/wordmark.png" alt="Phanometer" />
        <div className="footer-disclaimer">
          No affiliation with the Phillies, MLB, news publications, or media platforms.
        </div>
      </div>

      <div className="footer-methodology">
        <div className="footer-h">Methodology</div>
        <p>
          Each day, Phan-o-meter pulls from public sources — MLB Stats API for scores and gate
          figures, and publicly available podcast and YouTube feeds — and scores seven dimensions
          of fan mood on a 0–100 scale. The composite is a weighted blend of those dimensions;
          voice breakdowns capture how each constituency (fans, beat writers, analysts, talk
          radio) is reading the team that day.
        </p>
        <p>
          Scoring summaries and thematic write-ups are mostly AI-generated. AI can hallucinate —
          treat daily color commentary as directional, not gospel. Hard numbers (scores,
          attendance, capacity %) come straight from the API.
        </p>
      </div>

      <div className="footer-meta">
        <div>
          Send feedback to{' '}
          <a href="https://instagram.com/phanometer" target="_blank" rel="noopener noreferrer">
            @phanometer
          </a>{' '}
          on Instagram
        </div>
        <div>Generated {formatTime(generatedAt)}</div>
        <div>© 2026 Phan-o-meter</div>
      </div>
    </footer>
  );
}
