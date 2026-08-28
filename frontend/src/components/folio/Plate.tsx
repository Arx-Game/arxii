import * as React from 'react';

import { cn } from '@/lib/utils';

export type PlateProps = React.HTMLAttributes<HTMLDivElement>;

/**
 * Commonplace Book folio primitive (#3412, Direction B — ratified 2026-08-28).
 *
 * The base surface for the Hall's plates/tiles: a square-cornered card with a
 * hairline 1px border and no shadow (the folio idiom deliberately rejects the
 * rounded/elevated shadcn `Card` look). Colors flow entirely through the realm
 * tokens (`bg-card`/`border`) so the surface holds in every realm and both
 * light/dark mode by construction — never a literal color here.
 *
 * Deliberately a bare styled `div`, not a composition of `ui/card.tsx`
 * (`Card` bakes in `rounded-xl` + `shadow`, both banned by the ruling).
 */
export function Plate({ className, children, ...props }: PlateProps) {
  return (
    <div
      className={cn('rounded-none border bg-card text-card-foreground shadow-none', className)}
      {...props}
    >
      {children}
    </div>
  );
}
