/** Entries, not cards (#3540): a details/summary index entry with reading first, choosing second. */
import type { ReactNode } from 'react';
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
  children: ReactNode;
}

export function Entry({ name, gloss, tag, chosen, closed, open, children }: EntryProps) {
  return (
    <li className={[chosen ? 'chosen' : '', closed ? 'closed' : ''].join(' ').trim()}>
      <details className="entry" open={open}>
        <summary>
          <span className="entry-head">
            <span className="entry-name">{name}</span>
            {gloss && <span className="entry-gloss">{gloss}</span>}
          </span>
          <span className="entry-tag">
            <span>{tag}</span>
            {!closed && (
              <span className="chosen-tag">
                <span className="orn" aria-hidden="true">
                  ❧
                </span>{' '}
                Chosen
              </span>
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
  onSetAside: () => void;
  quiet?: { label: string; to: string };
}

export function EntryDoors({ chooseLabel, onChoose, chosen, onSetAside, quiet }: EntryDoorsProps) {
  return (
    <div className="entry-act">
      <button type="button" className="btn-small" aria-pressed={chosen} onClick={onChoose}>
        {chooseLabel}
      </button>
      <span className="chosen-line">
        Chosen.{' '}
        <button type="button" onClick={onSetAside}>
          Set it aside.
        </button>
      </span>
      {quiet && (
        <Link className="quiet-link" to={quiet.to}>
          {quiet.label}
        </Link>
      )}
    </div>
  );
}
