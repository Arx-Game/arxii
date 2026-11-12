/**
 * RecordRail (#3983 Task 9, plates S-III to S-VII's `aside.record`): the
 * "on record" `<dl>` and a "links" list, shared by every leaf. Each leaf
 * builds its `rows` and `doors` from what its document carries; a fact the
 * document has no field for gets no row.
 *
 * A door always goes somewhere (#5090): it carries a route or a same-page
 * action, and a leaf with nowhere to send it leaves it out. An "on record"
 * section with no rows is not drawn.
 */
import { Fragment, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

export interface RecordRailRow {
  label: string;
  value: ReactNode;
}

export type RecordRailDoor = {
  label: string;
  small?: string;
} & (
  | { /** A route to link to. */ to: string; onClick?: undefined }
  | { /** A same-page action. */ onClick: () => void; to?: undefined }
);

interface RecordRailSection {
  heading: string;
  rows: RecordRailRow[];
}

export interface RecordRailProps {
  rows: RecordRailRow[];
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
  return (
    <button type="button" onClick={door.onClick}>
      {door.label}
      {door.small && <small>{door.small}</small>}
    </button>
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

export function RecordRail({ rows, doors = [] }: RecordRailProps) {
  return (
    <aside className="record">
      {rows.length > 0 && <Section heading="on record" rows={rows} />}
      {doors.length > 0 && (
        <>
          <h4>links</h4>
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
