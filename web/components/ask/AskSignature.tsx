interface AskSignatureProps {
  slug: string;
}

export function AskSignature({ slug }: AskSignatureProps) {
  return (
    <div className="ask-signature">
      <div className="em">— Phan-o-meter, reading from the daily record.</div>
      <div style={{ marginTop: 8 }}>
        <span className="permalink">phanometer.com/ask/{slug}</span>
      </div>
    </div>
  );
}
