import * as React from 'react';

import { cn } from '@/lib/utils';

export interface PlateHeadProps extends React.HTMLAttributes<HTMLElement> {
  /** Element/component to render as (default `div`) — callers own heading semantics. */
  as?: React.ElementType;
}

/**
 * Commonplace Book folio primitive (#3412, Direction B — ratified 2026-08-28).
 *
 * A `Plate`'s small-caps label strip: the identity/heading voice (Cinzel, via
 * the existing `.theme-heading` utility — it already maps to the display font
 * and degrades to plain text under `[data-plain-mode]`), 0.78rem, uppercase,
 * 0.24em tracking, muted. `as` defaults to `div` rather than assuming a
 * heading level — a Plate can sit anywhere in a page's outline, so the caller
 * decides (`as="h2"`, `as="h3"`, ...) when it needs to be one.
 */
export function PlateHead({
  as: Component = 'div',
  className,
  children,
  ...props
}: PlateHeadProps) {
  return (
    <Component
      className={cn(
        'theme-heading text-[0.78rem] uppercase tracking-[0.24em] text-muted-foreground',
        className
      )}
      {...props}
    >
      {children}
    </Component>
  );
}
