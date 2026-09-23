/**
 * RecordSoFar (#3983 Plan B Task 4, plates F-II onward `.record .sofar`) —
 * the founder's own choices quoted back as a running summary on the right
 * rail once a seat is claimed. Composes nothing the founder hasn't written;
 * a section nothing has been entered for yet prints as a `.todo` entry
 * instead of guessing at what Tasks 5-6's House/Family/Land/Estate chapters
 * will eventually fill in.
 *
 * Task 5 fold-in: `quiddityName`/`features`/`youName` are optional — a
 * caller on the Seat step (before a template or a founder placement exist)
 * passes none of them and the rail renders exactly as it did before. Once
 * the House/Family chapters are reached, `FounderHouseChapter`/
 * `FounderFamilyChapter`'s own callers (Task 6's wiring) pass them, adding
 * plate F-II's "quiddity" row + "features" `<dl>` and plate F-III's "you"
 * row + "linked houses" `<dl>`.
 *
 * `step` (fix round 1, Finding M1) — the shell (`FounderAlmanach.tsx`)
 * always knows which chapter is current, so it's the one place that can
 * tell "house" and "quiddity" apart: on the House step itself (plate F-II)
 * they're two separate rows (the quiddity is a live, still-changeable pick
 * sitting right there in the same chapter); from the Family step on (plate
 * F-III onward, where the House chapter itself is out of view) they read as
 * one settled fact, "Candela · the Veiled". Omitting `step` (or passing
 * `'house'`/`'seat'`) keeps the two-row form.
 */
import { Fragment } from 'react';

import type { FounderDraft } from './founderDraft';
import type { FounderStep } from './steps';

export interface RecordSoFarProps {
  draft: FounderDraft;
  /** The claimed seat's own name, e.g. "Fervor" — '' before a seat is picked. */
  seatName: string;
  /** Who the seat is sworn to, e.g. "Piropa" — '' when unknown. */
  swornTo: string;
  /** The picked template's first aspect definition's chosen option name
   * (plate F-II's "quiddity" row) — omitted before a template/pick exist. */
  quiddityName?: string;
  /** The picked template's own cultural features (plate F-II's "features"
   * `<dl>`) — omitted before a template is picked. */
  features?: { name: string; codexEntryId: number | null }[];
  /** The founder's own name (plate F-III's "you" row) — omitted before the
   * Family chapter is reached. See `FounderHouseChapter`'s own doc comment
   * on why this is always the literal `'Given name'` today. */
  youName?: string;
  /** The chassis's current chapter — decides the house/quiddity row split
   * (see the module doc comment). Omitted keeps the two-row House-step form. */
  step?: FounderStep;
}

export function RecordSoFar({
  draft,
  seatName,
  swornTo,
  quiddityName,
  features,
  youName,
  step,
}: RecordSoFarProps) {
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

  // Plate F-II (the House step itself) keeps "house"/"quiddity" as two
  // rows; plate F-III on combines them into one settled "Candela · the
  // Veiled" line (see the module doc comment).
  const combineHouseAndQuiddity = step != null && step !== 'seat' && step !== 'house';
  if (draft.house_name !== '') {
    entries.push({
      q: 'house',
      text:
        combineHouseAndQuiddity && quiddityName != null
          ? `${draft.house_name} · ${quiddityName}`
          : draft.house_name,
    });
  } else {
    todos.push('the house');
  }

  if (quiddityName != null && !combineHouseAndQuiddity) {
    entries.push({ q: 'quiddity', text: quiddityName });
  }

  if (
    draft.house_name !== '' &&
    (draft.words === '' || draft.colors === '' || draft.sigil_description === '')
  ) {
    todos.push('words, colors, sigil');
  }

  const head = draft.kin.find((kin) => kin.relation === 'head');
  if (head) {
    entries.push({ q: 'head', text: head.name });
  } else {
    todos.push('the family');
  }

  if (youName != null) {
    entries.push({ q: 'you', text: `${youName} · ${draft.founder_is_heir ? 'heir' : 'younger'}` });
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

  // Plate F-III's "linked houses" `<dl>` — every kin born into a house
  // other than the one being founded, grouped by that house's name.
  const linkedHouses = new Map<string, string[]>();
  for (const kin of draft.kin) {
    if (kin.born_into_name === '') continue;
    const list = linkedHouses.get(kin.born_into_name) ?? [];
    list.push(kin.name);
    linkedHouses.set(kin.born_into_name, list);
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
      {features != null && features.length > 0 && (
        <>
          <h4>features</h4>
          <dl>
            {features.map((feature) => (
              <Fragment key={feature.name}>
                <dt>{feature.name}</dt>
                <dd>
                  {feature.codexEntryId != null ? (
                    <a href={`/codex/${feature.codexEntryId}`}>codex</a>
                  ) : (
                    <abbr title="none">—</abbr>
                  )}
                </dd>
              </Fragment>
            ))}
          </dl>
        </>
      )}
      {linkedHouses.size > 0 && (
        <>
          <h4>linked houses</h4>
          <dl>
            {Array.from(linkedHouses.entries()).map(([houseName, names]) => (
              <Fragment key={houseName}>
                <dt>{houseName}</dt>
                {/* No staff route a founder can open a house on yet (Plan B
                    is a player-facing surface) — the name prints without a
                    link, unlike the staff Almanach's own "open" doors. */}
                <dd>{names.map((name) => `${name}, born`).join(' · ')}</dd>
              </Fragment>
            ))}
          </dl>
        </>
      )}
    </aside>
  );
}
