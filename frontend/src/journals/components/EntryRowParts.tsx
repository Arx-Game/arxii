/**
 * The Reading Room's row, as parts (#3941, extracted #3957).
 *
 * A row is a band, a meta line, a title and a clamped body. `JournalRow` draws one for a
 * `JournalEntrySummary`; `TieStream` draws one for a `TieStreamItem`, which is a
 * different shape entirely — it has no tags, no responses, no retort predicate, and its
 * band says which tier a capstone claimed rather than which CG introduction it is. The
 * two cannot share a component that takes an entry, so they share the presentation
 * instead: one spelling of the classes, one spelling of "Black journal".
 *
 * Every class here is either Tailwind on the realm tokens or a `.journals`-scoped `jr-*`
 * rule (`journals.css`), so anything rendering these must sit inside `.journals` — which
 * is the whole reason the tie page's stream roots itself in that class.
 */
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/** The band a private entry wears, in both places that draw one. */
export const BLACK_JOURNAL_BAND = 'Black journal';

/** The `<article>`'s own classes: hairline-separated, night ground when private. */
export function entryRowClass({
  isBlack,
  isRevealed,
}: {
  isBlack?: boolean;
  isRevealed?: boolean;
} = {}): string {
  return cn(
    'grid gap-[.35rem] border-t py-[1.1rem] first:border-t-0 first:pt-0',
    isBlack && 'jr-black my-[.35rem] border-t-0 px-5',
    isRevealed && 'border-l-[3px] border-l-primary pl-4'
  );
}

/** What the row is, above everything else. Absent when the row is an ordinary one. */
export function EntryBand({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return (
    <div
      className={cn(
        'jr-sans jr-soft text-[.6875rem] uppercase tracking-[.14em] text-muted-foreground',
        accent && 'text-primary'
      )}
    >
      {children}
    </div>
  );
}

/** Who wrote it and when. Both are nodes: one side links, the other flips. */
export function EntryMeta({ who, date }: { who?: ReactNode; date: ReactNode }) {
  return (
    <div className="jr-sans jr-soft flex flex-wrap items-baseline gap-x-[.9rem] gap-y-1 text-[.8125rem] text-muted-foreground">
      {who && (
        <span className="jr-strong font-body text-[1.05rem] font-semibold text-foreground">
          {who}
        </span>
      )}
      <span>{date}</span>
    </div>
  );
}

/** The title. `quiet` is the smaller italic a scene's name takes. */
export function EntryTitle({ children, quiet }: { children: ReactNode; quiet?: boolean }) {
  return (
    <h3
      className={cn(
        'm-0 font-body leading-[1.2]',
        quiet ? 'text-[1.1rem] italic' : 'text-[1.4rem] font-medium'
      )}
    >
      {children}
    </h3>
  );
}

/** The text, keeping its own paragraphing, cut to seven lines while collapsed. */
export function EntryBody({ children, clamped }: { children: ReactNode; clamped?: boolean }) {
  return <div className={cn('jr-body font-body', clamped && 'jr-clamp')}>{children}</div>;
}
