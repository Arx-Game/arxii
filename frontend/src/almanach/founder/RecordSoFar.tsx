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
  /** The plate's own "the land" line (`steps.ts`'s `landBaseLine`,
   * `<top> · <n> baronies · seat <name>, <hall>`) — omitted before the Land
   * chapter is reached, matching plates F-II/F-III's own `.todo` "the land"
   * row (#3983 Plan B Task 6). When provided (even `''`), it replaces the
   * placeholder "N holdings" count below outright — the caller decides when
   * the real line is known. */
  landText?: string;
  /** The plate's own "the estate" line (`<name> · <capital>`) — omitted
   * before the Estate chapter is reached, matching plates F-II through F-IV's
   * own `.todo` "the estate" row (#3983 Plan B Task 6). */
  estateText?: string;
}

type RecordEntry = { q: string; text: string };
type RecordSummary = { entries: RecordEntry[]; todos: string[] };

function addSeatAndHouse(summary: RecordSummary, props: RecordSoFarProps): void {
  const { draft, seatName, swornTo, quiddityName, step } = props;
  if (seatName !== '') {
    summary.entries.push({
      q: 'seat',
      text: swornTo !== '' ? `${seatName} · sworn to ${swornTo}` : seatName,
    });
  } else summary.todos.push('the seat');

  const combine = step != null && step !== 'seat' && step !== 'house';
  if (draft.house_name !== '') {
    summary.entries.push({
      q: 'house',
      text:
        combine && quiddityName != null
          ? `${draft.house_name} · ${quiddityName}`
          : draft.house_name,
    });
  } else summary.todos.push('the house');
  if (quiddityName != null && !combine) summary.entries.push({ q: 'quiddity', text: quiddityName });
  if (
    draft.house_name !== '' &&
    (draft.words === '' || draft.colors === '' || draft.sigil_description === '')
  ) {
    summary.todos.push('words, colors, sigil');
  }
}

function addFamilySummary(summary: RecordSummary, props: RecordSoFarProps): void {
  const { draft, youName } = props;
  const head = draft.kin.find((kin) => kin.relation === 'head');
  if (head) summary.entries.push({ q: 'head', text: head.name });
  else summary.todos.push('the family');
  if (youName == null) return;
  let place = draft.founder_is_heir ? 'heir' : 'younger';
  if (draft.founder_relation === 'head') place = 'head of house';
  summary.entries.push({ q: 'you', text: `${youName} · ${place}` });
}

function addLandAndEstateSummary(summary: RecordSummary, props: RecordSoFarProps): void {
  const { draft, landText, estateText } = props;
  if (landText != null) summary.entries.push({ q: 'the land', text: landText });
  else {
    const count = Object.keys(draft.lands).length;
    if (count > 0)
      summary.entries.push({
        q: 'the land',
        text: `${count} ${count === 1 ? 'holding' : 'holdings'}`,
      });
    else summary.todos.push('the land');
  }
  if (estateText != null) summary.entries.push({ q: 'the estate', text: estateText });
  else if (draft.estate_name !== '')
    summary.entries.push({ q: 'the estate', text: draft.estate_name });
  else summary.todos.push('the estate');
}

function linkedHousesOf(draft: FounderDraft): Map<string, string[]> {
  const linked = new Map<string, string[]>();
  for (const kin of draft.kin) {
    if (kin.born_into_name === '') continue;
    const names = linked.get(kin.born_into_name) ?? [];
    names.push(kin.name);
    linked.set(kin.born_into_name, names);
  }
  return linked;
}

function summaryOf(props: RecordSoFarProps): RecordSummary {
  const summary: RecordSummary = { entries: [], todos: [] };
  addSeatAndHouse(summary, props);
  addFamilySummary(summary, props);
  addLandAndEstateSummary(summary, props);
  return summary;
}

export function RecordSoFar(props: RecordSoFarProps) {
  const { draft, features } = props;
  const { entries, todos } = summaryOf(props);
  const linkedHouses = linkedHousesOf(draft);

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
