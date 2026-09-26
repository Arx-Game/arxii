/** Entries, not cards (#3540): a details/summary index entry with reading first, choosing second. */
import type { MouseEvent, ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function EntryList({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul className="entry-list" aria-label={label}>
      {children}
    </ul>
  );
}

interface EntryProps {
  name: string;
  gloss?: string;
  tag: string;
  chosen: boolean;
  /** A gated entry: readable, not choosable. */
  closed?: boolean;
  open?: boolean;
  /** An icon or mark shown before the name, decorative only. */
  lead?: ReactNode;
  /**
   * The Select mark in the name row (#4022). Present, the row carries a square
   * mark that reads Select, or a checked Selected once chosen, and pressing it
   * chooses (or clears, when `onSetAside` is given) without opening the entry.
   * The maintainer's walkthrough found the foot door alone too easy to miss.
   */
  onChoose?: () => void;
  /** Omit for a choice the API cannot clear; the chosen mark is then inert. */
  onSetAside?: () => void;
  children: ReactNode;
}

export function Entry({
  name,
  gloss,
  tag,
  chosen,
  closed,
  open,
  lead,
  onChoose,
  onSetAside,
  children,
}: EntryProps) {
  const pressMark = (event: MouseEvent<HTMLButtonElement>) => {
    // Inside <summary>, a click also toggles the disclosure; the mark must not.
    event.preventDefault();
    event.stopPropagation();
    if (chosen) {
      onSetAside?.();
    } else {
      onChoose?.();
    }
  };
  return (
    <li className={[chosen ? 'chosen' : '', closed ? 'closed' : ''].join(' ').trim()}>
      <details className="entry" open={open}>
        <summary>
          <span className="entry-head">
            {lead && (
              <span className="entry-lead" aria-hidden="true">
                {lead}
              </span>
            )}
            <span className="entry-name">{name}</span>
            {gloss && <span className="entry-gloss">{gloss}</span>}
          </span>
          <span className="entry-tag">
            <span>{tag}</span>
            {!closed && onChoose && (
              <button
                type="button"
                className="entry-mark"
                aria-pressed={chosen}
                aria-label={`${chosen ? 'Selected' : 'Select'} ${name}`}
                disabled={chosen && !onSetAside}
                onClick={pressMark}
              >
                <span className="mark-box" aria-hidden="true">
                  {chosen ? '✓' : ''}
                </span>
                {chosen ? 'Selected' : 'Select'}
              </button>
            )}
          </span>
        </summary>
        <div className="entry-prose">{children}</div>
      </details>
    </li>
  );
}

interface EntryDoorsProps {
  chooseLabel: string;
  onChoose: () => void;
  chosen: boolean;
  /** Omit for a choice the API cannot clear; the chosen entry then shows no foot door. */
  onSetAside?: () => void;
  quiet?: { label: string; to: string };
}

/**
 * The door at the foot of the reading: one button, Select before the choice
 * and Clear after it (#4022 dropped the "Selected." sentence, which read as a
 * control and was not one).
 */
export function EntryDoors({ chooseLabel, onChoose, chosen, onSetAside, quiet }: EntryDoorsProps) {
  return (
    <div className="entry-act">
      {!chosen && (
        <button type="button" className="btn-small" aria-pressed={false} onClick={onChoose}>
          {chooseLabel}
        </button>
      )}
      {chosen && onSetAside && (
        <button type="button" className="btn-small" onClick={onSetAside}>
          Clear
        </button>
      )}
      {quiet && (
        <Link className="quiet-link" to={quiet.to}>
          {quiet.label}
        </Link>
      )}
    </div>
  );
}
