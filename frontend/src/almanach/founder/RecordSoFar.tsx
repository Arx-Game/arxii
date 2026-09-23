/**
 * RecordSoFar (#3983 Plan B Task 4, plates F-II onward `.record .sofar`) —
 * the founder's own choices quoted back as a running summary on the right
 * rail once a seat is claimed. Composes nothing the founder hasn't written;
 * a section nothing has been entered for yet prints as a `.todo` entry
 * instead of guessing at what Tasks 5-6's House/Family/Land/Estate chapters
 * will eventually fill in.
 */
import type { FounderDraft } from './founderDraft';

export interface RecordSoFarProps {
  draft: FounderDraft;
  /** The claimed seat's own name, e.g. "Fervor" — '' before a seat is picked. */
  seatName: string;
  /** Who the seat is sworn to, e.g. "Piropa" — '' when unknown. */
  swornTo: string;
}

export function RecordSoFar({ draft, seatName, swornTo }: RecordSoFarProps) {
  const entries: { q: string; text: string }[] = [];
  const todos: string[] = [];

  if (seatName !== '') {
    entries.push({
      q: 'seat',
      text: swornTo !== '' ? `${seatName} · sworn to ${swornTo}` : seatName,
    });
  } else {
    todos.push('the seat');
  }

  if (draft.house_name !== '') {
    entries.push({ q: 'house', text: draft.house_name });
  } else {
    todos.push('the house');
  }

  const head = draft.kin.find((kin) => kin.relation === 'head');
  if (head) {
    entries.push({ q: 'head', text: head.name });
  } else {
    todos.push('the family');
  }

  const landCount = Object.keys(draft.lands).length;
  if (landCount > 0) {
    entries.push({
      q: 'the land',
      text: `${landCount} ${landCount === 1 ? 'holding' : 'holdings'}`,
    });
  } else {
    todos.push('the land');
  }

  if (draft.estate_name !== '') {
    entries.push({ q: 'the estate', text: draft.estate_name });
  } else {
    todos.push('the estate');
  }

  return (
    <aside className="record">
      <h4>the record, so far</h4>
      <ul className="sofar">
        {entries.map((entry) => (
          <li key={entry.q}>
            <span className="q">{entry.q}</span>
            {entry.text}
          </li>
        ))}
        {todos.map((todo) => (
          <li className="todo" key={todo}>
            {todo}
          </li>
        ))}
      </ul>
    </aside>
  );
}
