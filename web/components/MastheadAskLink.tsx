'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

/**
 * The "Ask the crowd →" entry in the masthead. Active state (red, bold)
 * applies whenever the user is on /ask (with or without a query). Rendered as
 * a sibling of the @phanometer link inside .topbar-right (which uses a
 * stacked flex column layout).
 */
export function MastheadAskLink() {
  const pathname = usePathname();
  const isActive = pathname === '/ask' || pathname?.startsWith('/ask/');
  return (
    <Link href="/ask" className={`ask-link${isActive ? ' is-active' : ''}`}>
      Ask the crowd →
    </Link>
  );
}
