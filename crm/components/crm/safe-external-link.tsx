import type { ReactNode } from "react";
import { safeExternalUrl } from "@/lib/safe-url";

/**
 * External link that only becomes an anchor for http, https and mailto values.
 * Anything else renders as plain text so no unsafe href reaches the DOM.
 */
export function SafeExternalLink({
  href,
  children,
  className,
}: {
  href: string | null | undefined;
  children: ReactNode;
  className?: string;
}) {
  const safe = safeExternalUrl(href);
  if (!safe) {
    return href ? <span className="text-sm text-muted-foreground break-all">{href}</span> : null;
  }
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  );
}
