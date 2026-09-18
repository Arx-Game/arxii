/**
 * Display primitives for the Reference Sheet (#3898).
 *
 * These are read-only siblings of character creation's folio primitives
 * (`frontend/src/character-creation/folio/`). They are not shared with those on
 * purpose: CG's `Entry` is a selection control with a chosen state and doors, because
 * the interview asks the player to pick. The sheet only ever describes, so its entry
 * takes no handlers and has no state — giving the CG component a "display-only" mode
 * would put a wizard's vocabulary on a page that never chooses.
 *
 * Every one of these renders nothing when it has nothing (render-or-vanish): the sheet
 * has no empty-state cards apologising for a section the character has not filled in.
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** A tracked-caps label above a block. */
export function Eyebrow({ children }: { children: ReactNode }) {
  return <span className="refsheet-eyebrow">{children}</span>;
}

/** A section heading inside a panel. */
export function Heading({ children }: { children: ReactNode }) {
  return <h2 className="refsheet-heading">{children}</h2>;
}

/**
 * A quiet line in the world's bookkeeping voice — counts, states, "none of these".
 * Never a stat badge.
 */
export function Ledger({ children }: { children: ReactNode }) {
  return <p className="refsheet-ledger">{children}</p>;
}

/** A small uppercase tag. `accent` marks the one that matters on a row. */
export function Tag({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return <span className={cn('refsheet-tag', accent && 'refsheet-tag-accent')}>{children}</span>;
}

export interface GlanceRow {
  label: string;
  /** Rendered as-is; a falsy value drops the whole row rather than printing "TBD". */
  value: ReactNode;
}

/**
 * A label/value list. Rows with no value are dropped — the old sheet printed "TBD"
 * down a column of unfilled fields, which told the reader nothing and made every new
 * character look unfinished.
 */
export function Glance({ rows }: { rows: GlanceRow[] }) {
  const filled = rows.filter(
    (row) => row.value !== null && row.value !== undefined && row.value !== ''
  );
  if (filled.length === 0) return null;
  return (
    <dl className="refsheet-glance">
      {filled.map((row) => (
        <div key={row.label} style={{ display: 'contents' }}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

interface EntryProps {
  /** The row's name. A `to` turns it into a link. */
  name: ReactNode;
  tags?: ReactNode;
  /** A short line under the name, in the muted reading voice. */
  gloss?: ReactNode;
  /** Pulled to the right of the name — a rank, a status. */
  aside?: ReactNode;
  children?: ReactNode;
}

/** One hairline-separated index row. Wrap a run of them in `Entries`. */
export function Entry({ name, tags, gloss, aside, children }: EntryProps) {
  return (
    <div className="refsheet-entry">
      {aside ? (
        <div className="refsheet-entry-head">
          <span className="refsheet-entry-name">{name}</span>
          {aside}
        </div>
      ) : (
        <span className="refsheet-entry-name">{name}</span>
      )}
      {tags && <div className="refsheet-tags">{tags}</div>}
      {gloss && <p className="refsheet-entry-gloss">{gloss}</p>}
      {children}
    </div>
  );
}

/** A run of entries, closed by a hairline. Absent when it holds nothing. */
export function Entries({ children }: { children: ReactNode }) {
  return <div className="refsheet-entries">{children}</div>;
}

interface BandProps {
  title: string;
  /** The line beside the title: who may read this, or what it is for. */
  note?: ReactNode;
  /** Bands open by default — folding is a reader's convenience, not a barrier. */
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * A full-width folding band.
 *
 * Gated material lives in these rather than in the columns: a band keeps the three
 * columns short and even, and a viewer who may not read one never sees it at all —
 * the caller simply does not render it.
 */
export function Band({ title, note, defaultOpen = true, children }: BandProps) {
  return (
    <details className="refsheet-band" open={defaultOpen}>
      <summary>
        <Eyebrow>{title}</Eyebrow>
        {note && <span className="refsheet-note">{note}</span>}
      </summary>
      <div className="refsheet-band-body">{children}</div>
    </details>
  );
}

/** A column of blocks inside a panel. `wide` spaces the blocks further apart. */
export function Stack({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return <div className={wide ? 'refsheet-stack-wide' : 'refsheet-stack'}>{children}</div>;
}

/** Prose: description, background, anything written to be read. */
export function Prose({ children }: { children: ReactNode }) {
  return <div className="refsheet-prose">{children}</div>;
}
