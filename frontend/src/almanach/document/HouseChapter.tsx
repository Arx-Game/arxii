/**
 * HouseChapter (#3983 Task 9, plate S-III "The House") — the house's own
 * charter block: state, particle, succession, words/colors, sigil and house
 * prose, Quiddity, features, offices. Every editable field is staged
 * locally and the one savebar dispatches `almanach_edit_house` with only
 * the fields that actually changed (the action is a genuine partial patch —
 * `AlmanachEditHouseAction.execute`, `almanach.py`: an absent kwarg leaves
 * the column untouched, unlike `almanach_edit_kin`'s full-overwrite update).
 *
 * Charter answers (#5064): `house.charter_questions` is the catalog the house may
 * answer from, every question attached to a Family Template of its realm with
 * its options; `house.facets` is what it has answered. A single-pick question is
 * a select, a several-pick one is pressed chips capped at `max_picks`; the chosen
 * options list beneath with their blurb and codex link. The picks are staged like
 * the state toggle and the savebar sends `facet_option_ids`, the house's whole
 * list, only when it changed (the action replaces the rows wholesale). An answer
 * whose question is not in the catalog (a house whose realm has no templates)
 * renders read-only.
 *
 * The patron question (#5110, `sets_patron`) is the same select over a different
 * catalog: its options are the gods of the question's worship, their `id` a god's.
 * Its pick is `house.patron`, never a facet, and is sent as `patron_being_id`.
 *
 * Two ABSENT-catalog omissions remain, same root cause: nothing in the wire
 * payload lists the pickable rows.
 * - Features: `HouseFeature` has no list endpoint here — the chips render
 *   `house.features`, and the plate's own `⊕` add-a-feature chip is inert.
 * - Succession: `default_succession_law` gives only the CURRENT law's
 *   name/codex id, never a `SuccessionLaw` catalog to pick a different one
 *   from — it renders as a read-only name + codex link, no editing control.
 *
 * The feature inert door is a plain `disabled aria-disabled` button with no
 * `title` (review fix round 1, Finding I4 — a native `title` tooltip is
 * reserved for the `.tip`/`.bub` pattern per the global constraints; `disabled` + `aria-disabled` alone already
 * communicates "not available" without a second, unapproved hover-text channel).
 *
 * Gentry is the one exception, ordered explicitly: it is a live option of
 * the state select when `realmTheme === 'luxen'` (`_realm_payload`'s
 * `realm_theme`, final review I11 — Spec Decision 12 requires Gentry
 * reachable in Luxen), and stays a disabled option (`title="Luxen only"`)
 * for every other theme — a `title` here was ruled a keeper despite the
 * constraint. The state is one select rather than a row of tiles (#4533:
 * four tiles scrunched "In exile" and read as spread-out toggles).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useDraft } from '@/world-builder/document/useDraft';

import { HOUSE_STATES, GENTRY_LUXEN_ONLY, houseHeading, particlePair } from '../copy';
import { ObservanceRows, type ObservanceRow } from '../ObservanceRows';
import type { AlmanachHouseDocumentHouse } from '../types';
import { urls } from '@/utils/urls';

export interface EditHouseFields {
  name?: string;
  words?: string;
  colors?: string;
  sigil_description?: string;
  description?: string;
  house_state?: string;
  /** The whole list, replacing the house's days of remembrance (#4206). */
  observances?: ObservanceRow[];
  /** The whole list of charter answers, replacing the house's facets (#5064). */
  facet_option_ids?: number[];
  /** The god picked on the patron question, or null for none (#5110). */
  patron_being_id?: number | null;
}

/** The house's answers by question id, the shape the pickers edit. */
type Picks = Record<number, number[]>;

function initialPicks(house: AlmanachHouseDocumentHouse): Picks {
  const picks: Picks = {};
  for (const facet of house.facets) {
    (picks[facet.definition_id] ??= []).push(facet.option_id);
  }
  // The patron question is answered with a god (#5110): its pick is the house's
  // patron, and the ids its select holds are gods' ids.
  const patronQuestion = house.charter_questions.find((question) => question.sets_patron);
  if (patronQuestion && house.patron) picks[patronQuestion.id] = [house.patron.being_id];
  return picks;
}

/** Every chosen option id, the catalog's questions first in their order, then any
 * answer to a question outside it (kept, since the action replaces the list). */
function flattenPicks(picks: Picks, house: AlmanachHouseDocumentHouse): number[] {
  const seen = new Set<number>();
  const out: number[] = [];
  const patronIds = new Set(house.charter_questions.filter((q) => q.sets_patron).map((q) => q.id));
  const questionIds = [
    ...house.charter_questions.map((q) => q.id),
    ...Object.keys(picks).map(Number),
  ];
  for (const id of questionIds) {
    // a patron pick is a god, sent as `patron_being_id`, never an option id
    if (seen.has(id) || patronIds.has(id)) continue;
    seen.add(id);
    out.push(...(picks[id] ?? []));
  }
  return out;
}

function sameSet(a: number[], b: number[]): boolean {
  return (
    JSON.stringify([...a].sort((x, y) => x - y)) === JSON.stringify([...b].sort((x, y) => x - y))
  );
}

/** The document's rows as the editor holds them: the spelled `when` dropped,
 * since the server derives it and the action does not take it. */
function editableObservances(house: AlmanachHouseDocumentHouse): ObservanceRow[] {
  return house.observances.map((row) => ({
    ic_month: row.ic_month,
    ic_day: row.ic_day,
    name: row.name,
    lore: row.lore,
  }));
}

export interface HouseChapterProps {
  house: AlmanachHouseDocumentHouse;
  /** `document.realm.realm_theme` (`_realm_payload`) — gates the Gentry
   * toggle: enabled only in a `'luxen'` realm, disabled everywhere else. */
  realmTheme: string;
  onSave: (fields: EditHouseFields) => void;
}

const STATE_CHOICES: { value: string; label: string }[] = [
  { value: 'standing', label: HOUSE_STATES.standing },
  { value: 'in_exile', label: HOUSE_STATES.in_exile },
  { value: 'extinct', label: HOUSE_STATES.extinct },
];

export function HouseChapter({ house, realmTheme, onSave }: HouseChapterProps) {
  const [houseState, setHouseState] = useState(house.house_state);
  const words = useDraft(house.id, 'house-words', house.words);
  const colors = useDraft(house.id, 'house-colors', house.colors);
  const sigil = useDraft(house.id, 'house-sigil_description', house.sigil_description);
  const description = useDraft(house.id, 'house-description', house.description);
  // The house's charter answers, grouped under the question each answers (#4533):
  // an Umbral house has no Quiddity, so the heading is the question's own name and
  // a house with no answers shows no block at all.
  const facetGroups = Array.from(
    house.facets.reduce((groups, aspect) => {
      const list = groups.get(aspect.definition) ?? [];
      list.push(aspect);
      return groups.set(aspect.definition, list);
    }, new Map<string, typeof house.facets>())
  );
  // Staged like the state toggle, not a per-field draft: the list is one value
  // and the action replaces it wholesale (#4206).
  const [observances, setObservances] = useState<ObservanceRow[]>(() => editableObservances(house));
  const [picks, setPicks] = useState<Picks>(() => initialPicks(house));
  const catalogIds = new Set(house.charter_questions.map((q) => q.id));
  const patronQuestion = house.charter_questions.find((question) => question.sets_patron);
  const readOnlyGroups = facetGroups.filter(
    ([, facets]) => !catalogIds.has(facets[0].definition_id)
  );

  const togglePick = (questionId: number, optionId: number, maxPicks: number) => {
    setPicks((prev) => {
      const current = prev[questionId] ?? [];
      if (current.includes(optionId)) {
        return { ...prev, [questionId]: current.filter((id) => id !== optionId) };
      }
      if (current.length >= maxPicks) return prev;
      return { ...prev, [questionId]: [...current, optionId] };
    });
  };

  const save = () => {
    const fields: EditHouseFields = {};
    if (houseState !== house.house_state) fields.house_state = houseState;
    if (words.value !== house.words) fields.words = words.value;
    if (colors.value !== house.colors) fields.colors = colors.value;
    if (sigil.value !== house.sigil_description) fields.sigil_description = sigil.value;
    if (description.value !== house.description) fields.description = description.value;
    if (JSON.stringify(observances) !== JSON.stringify(editableObservances(house)))
      fields.observances = observances;
    const chosen = flattenPicks(picks, house);
    if (
      !sameSet(
        chosen,
        house.facets.map((facet) => facet.option_id)
      )
    )
      fields.facet_option_ids = chosen;
    if (patronQuestion) {
      const pickedPatron = picks[patronQuestion.id]?.[0] ?? null;
      if (pickedPatron !== (house.patron?.being_id ?? null)) fields.patron_being_id = pickedPatron;
    }
    if (Object.keys(fields).length === 0) return;
    onSave(fields);
    if (fields.words !== undefined) words.clearDraft();
    if (fields.colors !== undefined) colors.clearDraft();
    if (fields.sigil_description !== undefined) sigil.clearDraft();
    if (fields.description !== undefined) description.clearDraft();
  };

  return (
    <main className="chapter">
      <h3>{houseHeading(house.name)}</h3>
      <div className="row3">
        <div className="field">
          <span className="label">state</span>
          <select
            id="house-state"
            aria-label="State"
            value={houseState}
            onChange={(e) => setHouseState(e.target.value)}
          >
            {STATE_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
            <option
              value="gentry"
              disabled={realmTheme !== 'luxen'}
              title={realmTheme === 'luxen' ? undefined : GENTRY_LUXEN_ONLY}
            >
              {HOUSE_STATES.gentry}
            </option>
          </select>
        </div>
        <div className="field">
          <span className="label">particle</span>
          <div className="val">
            {house.particle.born ? (
              particlePair(house.particle.born, house.particle.taken_in)
            ) : (
              <abbr title="none">—</abbr>
            )}
          </div>
        </div>
        <div className="field">
          <span className="label">succession</span>
          <div className="val">
            {house.default_succession_law ? (
              <>
                {house.default_succession_law.name}
                {house.default_succession_law.codex_entry_id != null && (
                  <>
                    {' '}
                    ·{' '}
                    <Link to={urls.codexEntry(house.default_succession_law.codex_entry_id)}>
                      codex
                    </Link>
                  </>
                )}
              </>
            ) : (
              <abbr title="none">—</abbr>
            )}
          </div>
        </div>
      </div>
      {/* The patron question below shows the god it picked; this line is for a
          house whose realm asks no patron question but which has a patron. */}
      {house.patron && !patronQuestion && (
        <div className="field">
          <span className="label">patron</span>
          <div className="val">
            {house.patron.codex_entry_id != null ? (
              <Link to={urls.codexEntry(house.patron.codex_entry_id)}>
                {house.patron.being_name}
              </Link>
            ) : (
              house.patron.being_name
            )}
          </div>
        </div>
      )}
      <div className="row2">
        <div className="field">
          <label htmlFor={`house-words-${house.id}`}>words</label>
          <input
            id={`house-words-${house.id}`}
            type="text"
            value={words.value}
            onChange={(event) => words.setValue(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={`house-colors-${house.id}`}>colors</label>
          <input
            id={`house-colors-${house.id}`}
            type="text"
            value={colors.value}
            onChange={(event) => colors.setValue(event.target.value)}
          />
        </div>
      </div>
      <div className="field">
        <label htmlFor={`house-sigil-${house.id}`}>sigil</label>
        <textarea
          id={`house-sigil-${house.id}`}
          className="prose short"
          rows={2}
          value={sigil.value}
          onChange={(event) => sigil.setValue(event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`house-description-${house.id}`}>description</label>
        <textarea
          id={`house-description-${house.id}`}
          className="prose"
          rows={6}
          value={description.value}
          onChange={(event) => description.setValue(event.target.value)}
        />
      </div>
      <ObservanceRows idPrefix={`house-${house.id}`} rows={observances} onChange={setObservances} />
      {house.charter_questions.map((question) => {
        const chosen = picks[question.id] ?? [];
        const chosenOptions = question.options.filter((option) => chosen.includes(option.id));
        const controlId = `house-facet-${house.id}-${question.id}`;
        return (
          <div className="field" key={question.id}>
            {question.max_picks === 1 ? (
              <>
                <label htmlFor={controlId}>{question.name}</label>
                <select
                  id={controlId}
                  value={chosen[0] ?? ''}
                  onChange={(event) =>
                    setPicks((prev) => ({
                      ...prev,
                      [question.id]: event.target.value === '' ? [] : [Number(event.target.value)],
                    }))
                  }
                >
                  <option value="">pick</option>
                  {question.options.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              <>
                <span className="label" id={`${controlId}-label`}>
                  {question.name}
                </span>
                <div className="chips" role="group" aria-labelledby={`${controlId}-label`}>
                  {question.options.map((option) => {
                    const on = chosen.includes(option.id);
                    return (
                      <button
                        type="button"
                        key={option.id}
                        className={on ? 'chip acc' : 'chip'}
                        aria-pressed={on}
                        onClick={() => togglePick(question.id, option.id, question.max_picks)}
                      >
                        {option.name}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
            {chosenOptions.length > 0 && (
              <ul className="entries compact">
                {chosenOptions.map((option) => (
                  <li key={option.id} className="on">
                    <span className="mark">◆</span>
                    <span>
                      {option.target_entry_id != null ? (
                        <Link to={urls.codexEntry(option.target_entry_id)} className="nm">
                          {option.name}
                        </Link>
                      ) : (
                        <span className="nm">{option.name}</span>
                      )}
                      <span className="ds">{option.description}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      {readOnlyGroups.map(([definition, facets]) => (
        <div className="field" key={definition}>
          <span className="label">{definition}</span>
          <ul className="entries compact">
            {facets.map((aspect) => (
              <li key={`${aspect.definition}-${aspect.option}`} className="on">
                <span className="mark">◆</span>
                <span>
                  {aspect.target_entry_id != null ? (
                    <Link to={urls.codexEntry(aspect.target_entry_id)} className="nm">
                      {aspect.option}
                    </Link>
                  ) : (
                    <span className="nm">{aspect.option}</span>
                  )}
                  <span className="ds">{aspect.description}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="field">
        <span className="label">features</span>
        <div className="chips">
          {house.features.map((feature) => (
            <span key={feature.slug} className="chip">
              {feature.name}
            </span>
          ))}
          <button
            type="button"
            className="chip acc"
            aria-label="Add a feature"
            disabled
            aria-disabled
          >
            ⊕
          </button>
        </div>
      </div>
      <div className="field">
        <span className="label">offices</span>
        <ul className="entries">
          {house.offices.map((office) => (
            <li key={office.slug}>
              <span className="mark" />
              <span>
                <span className="nm">{office.title}</span>
              </span>
              <span className="rt">
                {office.holder_name !== '' ? office.holder_name : 'Unclaimed'}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="savebar">
        <button type="button" className="btn" onClick={save}>
          Save
        </button>
      </div>
    </main>
  );
}
