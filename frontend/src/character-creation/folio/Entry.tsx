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
  /** An icon or mark shown before the name, decorative only. */
  lead?: ReactNode;
  children: ReactNode;
}

export function Entry({ name, gloss, tag, chosen, closed, open, lead, children }: EntryProps) {
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
            {!closed && (
              <span className="chosen-tag">
                <span className="orn" aria-hidden="true">
                  ❧
                </span>{' '}
                Selected
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
  /** Omit for a choice the API cannot clear; the chosen line then reads "Selected." with no button. */
  onSetAside?: () => void;
  quiet?: { label: string; to: string };
}

export function EntryDoors({ chooseLabel, onChoose, chosen, onSetAside, quiet }: EntryDoorsProps) {
  return (
    <div className="entry-act">
      <button type="button" className="btn-small" aria-pressed={chosen} onClick={onChoose}>
        {chooseLabel}
      </button>
      <span className="chosen-line">
        {onSetAside ? (
          <>
            Selected.{' '}
            <button type="button" onClick={onSetAside}>
              Clear
            </button>
          </>
        ) : (
          'Selected.'
        )}
      </span>
      {quiet && (
        <Link className="quiet-link" to={quiet.to}>
          {quiet.label}
        </Link>
      )}
    </div>
  );
}
