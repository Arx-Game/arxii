/**
 * HouseChapter (#3983 Task 9, plate S-III "The House") — the house's own
 * charter block: state, particle, succession, words/colors, sigil and house
 * prose, Quiddity, features, offices. Every editable field is staged
 * locally and the one savebar dispatches `almanach_edit_house` with only
 * the fields that actually changed (the action is a genuine partial patch —
 * `AlmanachEditHouseAction.execute`, `almanach.py`: an absent kwarg leaves
 * the column untouched, unlike `almanach_edit_kin`'s full-overwrite update).
 *
 * Three ABSENT-catalog omissions share one root cause: nothing in the wire
 * payload lists the pickable options.
 * - Quiddity: `house.aspects` gives only the house's OWN chosen
 *   definition/option/description triples, never the full
 *   `HouseAspectOption` catalog a "change" picker would need — the
 *   `.entries.compact` list renders the chosen options with their
 *   description folded in (only shown on `.on`) and an inert `⊕ change` door.
 * - Features: same shape (`HouseFeature` has no list endpoint here) — the
 *   chips render `house.features`, and the plate's own `⊕` add-a-feature
 *   chip is inert for the same reason.
 * - Succession: `default_succession_law` gives only the CURRENT law's
 *   name/codex id, never a `SuccessionLaw` catalog to pick a different one
 *   from — it renders as a read-only name + codex link, no editing control.
 *
 * The Quiddity/feature inert doors are plain `disabled aria-disabled`
 * buttons with no `title` (review fix round 1, Finding I4 — a native
 * `title` tooltip is reserved for the `.tip`/`.bub` pattern on the
 * particle/succession fields per the global constraints; `disabled` +
 * `aria-disabled` alone already communicates "not available" without a
 * second, unapproved hover-text channel).
 *
 * Gentry is the one exception, ordered explicitly: it toggles like every
 * other `state` choice when `realmTheme === 'luxen'` (`_realm_payload`'s new
 * `realm_theme`, final review I11 — Spec Decision 12 requires Gentry
 * reachable in Luxen), and stays disabled (`aria-disabled`,
 * `title="Luxen only"`) for every other theme — a `title` here was ruled a
 * keeper despite the constraint.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useDraft } from '@/world-builder/document/useDraft';

import { HOUSE_STATES, DRAFT_NOTE, GENTRY_LUXEN_ONLY } from '../copy';
import type { AlmanachHouseDocumentHouse } from '../types';

export interface EditHouseFields {
  name?: string;
  words?: string;
  colors?: string;
  sigil_description?: string;
  description?: string;
  house_state?: string;
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
  const particleGlossId = `house-particle-gloss-${house.id}`;

  const save = () => {
    const fields: EditHouseFields = {};
    if (houseState !== house.house_state) fields.house_state = houseState;
    if (words.value !== house.words) fields.words = words.value;
    if (colors.value !== house.colors) fields.colors = colors.value;
    if (sigil.value !== house.sigil_description) fields.sigil_description = sigil.value;
    if (description.value !== house.description) fields.description = description.value;
    if (Object.keys(fields).length === 0) return;
    onSave(fields);
    if (fields.words !== undefined) words.clearDraft();
    if (fields.colors !== undefined) colors.clearDraft();
    if (fields.sigil_description !== undefined) sigil.clearDraft();
    if (fields.description !== undefined) description.clearDraft();
  };

  return (
    <main className="chapter">
      <h3>House {house.name}</h3>
      <div className="row3">
        <div className="field">
          <span className="label">state</span>
          <div className="seg" role="group" aria-label="State">
            {STATE_CHOICES.map((choice) => (
              <button
                key={choice.value}
                type="button"
                aria-pressed={houseState === choice.value}
                onClick={() => setHouseState(choice.value)}
              >
                {choice.label}
              </button>
            ))}
            {realmTheme === 'luxen' ? (
              <button
                type="button"
                aria-pressed={houseState === 'gentry'}
                onClick={() => setHouseState('gentry')}
              >
                {HOUSE_STATES.gentry}
              </button>
            ) : (
              <button
                type="button"
                aria-pressed={false}
                disabled
                aria-disabled
                title={GENTRY_LUXEN_ONLY}
              >
                {HOUSE_STATES.gentry}
              </button>
            )}
          </div>
        </div>
        <div className="field">
          <span className="label">particle</span>
          <div className="val">
            <button type="button" className="tip" aria-describedby={particleGlossId}>
              worked example
              <span className="bub" id={particleGlossId}>
                {house.particle_example}
              </span>
            </button>
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
                    <Link to={`/codex/${house.default_succession_law.codex_entry_id}`}>codex</Link>
                  </>
                )}
              </>
            ) : (
              <abbr title="none">—</abbr>
            )}
          </div>
        </div>
      </div>
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
          className="prose"
          value={sigil.value}
          onChange={(event) => sigil.setValue(event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`house-description-${house.id}`}>the house</label>
        <textarea
          id={`house-description-${house.id}`}
          className="prose"
          value={description.value}
          onChange={(event) => description.setValue(event.target.value)}
        />
      </div>
      <div className="field">
        <span className="label">
          House Quiddity <span className="chip">seed copy · PLACEHOLDER</span>
        </span>
        <ul className="entries compact">
          {house.aspects.map((aspect) => (
            <li key={`${aspect.definition}-${aspect.option}`} className="on">
              <span className="mark">◆</span>
              <span>
                <span className="nm">{aspect.option}</span>
                <span className="ds">{aspect.description}</span>
              </span>
              <span className="rt">
                <button type="button" disabled aria-disabled>
                  ⊕ change
                </button>
              </span>
            </li>
          ))}
        </ul>
      </div>
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
        <span className="note">{DRAFT_NOTE}</span>
        <button type="button" className="btn" onClick={save}>
          Save
        </button>
      </div>
    </main>
  );
}
