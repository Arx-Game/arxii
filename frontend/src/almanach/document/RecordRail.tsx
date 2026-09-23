/**
 * RecordRail (#3983 Task 9, plates S-III to S-VII's `aside.record`) — the
 * generic "on record" `<dl>` plus an optional "doors" list, shared by every
 * leaf. Each leaf builds its own `rows`/`doors` from what the House Document
 * payload actually carries — several of the plate's own record-rail facts
 * (house nobility "kind", influence, recognition-rule text, remaining kin
 * slots, secondary "linked houses" memberships, treasury, pacts, unrest,
 * defenses, garrison) have no field anywhere in `HouseDocument` to read them
 * off, so those rows are left out rather than fabricated — see each leaf's
 * own comment for exactly which plate row that drops and why.
 */
import { Fragment, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

export interface RecordRailRow {
  label: string;
  value: ReactNode;
}

export interface RecordRailDoor {
  label: string;
  small?: string;
  /** A route to link to; omit and pass `onClick` for a same-page action instead. */
  to?: string;
  onClick?: () => void;
}

export interface RecordRailProps {
  rows: RecordRailRow[];
  doors?: RecordRailDoor[];
}

export function RecordRail({ rows, doors = [] }: RecordRailProps) {
  return (
    <aside className="record">
      <h4>on record</h4>
      <dl>
        {rows.map((row) => (
          <Fragment key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </Fragment>
        ))}
      </dl>
      {doors.length > 0 && (
        <>
          <h4>doors</h4>
          <ul className="doors">
            {doors.map((door) => (
              <li key={door.label}>
                {door.to ? (
                  <Link to={door.to}>
                    {door.label}
                    {door.small && <small>{door.small}</small>}
                  </Link>
                ) : (
                  <button type="button" onClick={door.onClick}>
                    {door.label}
                    {door.small && <small>{door.small}</small>}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
