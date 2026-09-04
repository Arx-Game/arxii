/** Your choices so far (#3540, Decision 8; OOC sweep): chosen values only, never prose. */
import type { ReactNode } from 'react';

export interface RecordRow {
  label: string;
  value?: string | null;
  /** When set, the value is a door back to the chapter that wrote it. */
  onEdit?: () => void;
}

function RecordValue({ value, onEdit }: { value?: string | null; onEdit?: () => void }) {
  if (!value) return <span className="unwritten">not yet chosen</span>;
  if (onEdit) {
    return (
      <button type="button" className="btn-quiet" onClick={onEdit}>
        {value}
      </button>
    );
  }
  return <>{value}</>;
}

export function RecordRail({ rows, ledger }: { rows: RecordRow[]; ledger?: string }) {
  return (
    <div className="record-rail">
      <h2 className="rail-label">Your choices so far</h2>
      <dl>
        {rows.map((row) => (
          <div className="row" key={row.label}>
            <dt>{row.label}</dt>
            <dd>
              <RecordValue value={row.value} onEdit={row.onEdit} />
            </dd>
          </div>
        ))}
      </dl>
      {ledger && <span className="rail-ledger">{ledger}</span>}
    </div>
  );
}

export function Marginalia({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <div className="note-group" id={id}>
      {children}
    </div>
  );
}

export function Note({ lead, children }: { lead: string; children?: ReactNode }) {
  return (
    <span className="note">
      <b>{lead}</b> {children}
    </span>
  );
}
