/**
 * RecordRail (#3983 Task 9, plates S-III to S-VII's `aside.record`) — the
 * generic "on record" `<dl>`, an optional second named section (Family's
 * "linked houses"), and an optional "doors" list, shared by every leaf.
 * Each leaf builds its own `rows`/`extraSection`/`doors` from what the
 * House Document payload actually carries — several of the plate's own
 * record-rail facts (house nobility "kind", influence, recognition-rule
 * text, remaining kin slots, secondary "linked houses" memberships,
 * treasury, pacts, unrest, defenses, garrison) have no field anywhere in
 * `HouseDocument` to read them off, so those rows show a dash rather than
 * fabricated content — see each leaf's own comment for exactly which plate
 * row that is and why.
 *
 * A door with neither `to` nor `onClick` (review fix round 1, Finding I2)
 * renders as a labeled dash instead — present on the page (the plate draws
 * it), but inert: nothing this app can link to or act on exists for it yet
 * ("the house on the roster", "the tree as players see it", "✎ the
 * secret", "the ladder" with no realm id to link back to, "open on the
 * Atlas" for an Estate with no area picker). A door with `to`/`onClick` set
 * renders as a real, working control, same as before.
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
  /** A route to link to; omit (with `onClick` too) for a same-page action,
   * or omit both for a not-yet-built destination (renders as a labeled dash). */
  to?: string;
  onClick?: () => void;
}

export interface RecordRailSection {
  heading: string;
  rows: RecordRailRow[];
}

export interface RecordRailProps {
  rows: RecordRailRow[];
  /** A second named `<dl>` section between "on record" and "doors" — only
   * Family's "linked houses" block uses this today. */
  extraSection?: RecordRailSection;
  doors?: RecordRailDoor[];
}

function DoorItem({ door }: { door: RecordRailDoor }) {
  if (door.to) {
    return (
      <Link to={door.to}>
        {door.label}
        {door.small && <small>{door.small}</small>}
      </Link>
    );
  }
  if (door.onClick) {
    return (
      <button type="button" onClick={door.onClick}>
        {door.label}
        {door.small && <small>{door.small}</small>}
      </button>
    );
  }
  return (
    <span className="faint">
      {door.label}
      {door.small && <small>{door.small}</small>} <abbr title="none">—</abbr>
    </span>
  );
}

function Section({ heading, rows }: RecordRailSection) {
  return (
    <>
      <h4>{heading}</h4>
      <dl>
        {rows.map((row) => (
          <Fragment key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </Fragment>
        ))}
      </dl>
    </>
  );
}

export function RecordRail({ rows, extraSection, doors = [] }: RecordRailProps) {
  return (
    <aside className="record">
      <Section heading="on record" rows={rows} />
      {extraSection && <Section heading={extraSection.heading} rows={extraSection.rows} />}
      {doors.length > 0 && (
        <>
          <h4>doors</h4>
          <ul className="doors">
            {doors.map((door) => (
              <li key={door.label}>
                <DoorItem door={door} />
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
