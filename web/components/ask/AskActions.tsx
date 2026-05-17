'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

export function AskActions() {
  const router = useRouter();
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return;
    navigator.clipboard
      .writeText(window.location.href)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {
        // Quietly no-op on clipboard permission failure; nothing to recover.
      });
  }

  return (
    <div className="ask-actions">
      <button
        type="button"
        className="primary"
        onClick={() => router.push('/ask')}
      >
        Ask another →
      </button>
      <button className="secondary" type="button" onClick={handleCopy}>
        {copied ? 'Copied' : 'Copy link'}
      </button>
    </div>
  );
}
