import * as React from 'react';

import { cn } from '@/lib/utils';

export interface CountChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  count: number;
  /**
   * The rest of the accessible sentence after the count, e.g. `"tidings waiting"`
   * so the rendered `title`/`aria-label` reads `"4 tidings waiting"`. Required —
   * a bare number is not an accessible fact on its own.
   */
  label: string;
}

/**
 * Commonplace Book folio primitive (#3412, Direction B — ratified 2026-08-28).
 *
 * A square (no radius) unread/count indicator. Data voice (default sans,
 * tabular-nums so digits don't jitter the layout as the count changes) inside
 * a PRIMARY-colored chip — ruled 2026-08-28: destructive red is reserved for
 * genuine danger, never spent on "you have mail." The portrait is the
 * load-bearing state signal; this chip's text is supporting copy, so the
 * `title`/`aria-label` pair always carries the same full sentence a screen
 * reader or tooltip needs ("N tidings waiting"), never just the digit.
 *
 * Renders nothing at `count <= 0` — an empty/zero chip is visual noise, not a
 * signal.
 */
export function CountChip({ count, label, className, ...props }: CountChipProps) {
  if (count <= 0) return null;

  const text = `${count} ${label}`;

  return (
    <span
      className={cn(
        'inline-flex min-w-[1.25rem] items-center justify-center rounded-none bg-primary',
        'px-1.5 py-0.5 text-xs font-medium tabular-nums leading-none text-primary-foreground',
        className
      )}
      title={text}
      aria-label={text}
      {...props}
    >
      {count}
    </span>
  );
}
