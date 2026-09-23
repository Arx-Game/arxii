/**
 * FounderPersonPanel (#3983 Plan B Task 5, plate F-III's `.panel`) — the
 * founder Family chapter's own `renderPanel` for `FamilyChapter`
 * (`document/FamilyChapter.tsx`'s `renderPanel` prop). Two shapes, by
 * whether the selected node is the founder's own (`FOUNDER_NODE_ID`,
 * `./familyShape`):
 *
 * - The founder's own row: a "you are" `.seg` (final review I4) writing
 *   `founder_relation` — head / child / sibling / spouse "of the head"
 *   (never mother/father/grandparent for the founder HERSELF; those stay
 *   reachable only as separate kin rows) — mother/father read straight off
 *   the shape as plain `.val` text (never editable here — they're edited by
 *   selecting THEIR OWN row instead, which falls through to the kin-edit
 *   panel below), a heir/younger `.seg` writing `founder_is_heir`
 *   (unchanged by I4 — still offered regardless of place), and "on the
 *   public record" chips, one per parent on record.
 * - Every other row (head, mother, father, spouse, sibling, child, a ward)
 *   is a `FounderKin` the founder wrote herself, so it's fully editable:
 *   name, gender, age, deceased, born into (a secondary house pick), and a
 *   Remove door. `keyByNodeId` (`founderFamilyShape`'s own output) maps the
 *   selected node's synthetic id back to the `FounderKin.key`
 *   `updateKin`/`removeKin` take; a household `position` row (an open slot
 *   with no holder) never reaches this panel at all — `FamilyChapter`'s own
 *   household rendering never opens one for selection.
 *
 * The generic `PersonPanel` this replaces treats `name` as read-only (no
 * action can rename a real `Kinsperson` through it) and renders three
 * public-record/in-truth/known-as rows that only make sense once a
 * `Kinsperson` and its secrets actually exist — none of that applies here:
 * nothing is a real `Kinsperson` yet, so every field the founder wrote is
 * hers to fix, and "on the public record" is the one secrecy-adjacent
 * concept a draft can express (whether the founder's own birth is
 * advertised, plate F-III's accent chips).
 */
import { useId } from 'react';

import type { ClaimKinRelation } from '@/character-creation/types';

import { useAllHouses, useGenders } from '../queries';
import type { AlmanachFamilyNode } from '../types';
import type { FounderDraft, FounderKin } from './founderDraft';
import { FOUNDER_NODE_ID } from './familyShape';
import type { UseFounderDraftResult } from './founderDraft';

/** The "you are" seg's four options (final review I4) — never
 * mother/father/grandparent for the founder herself (see module comment). */
const FOUNDER_PLACE_CHOICES: { value: ClaimKinRelation; label: string }[] = [
  { value: 'head', label: 'head of house' },
  { value: 'child', label: 'child' },
  { value: 'sibling', label: 'sibling' },
  { value: 'spouse', label: 'spouse' },
];

export interface FounderPersonPanelProps {
  node: AlmanachFamilyNode;
  draft: FounderDraft;
  keyByNodeId: Record<number, string>;
  updateKin: UseFounderDraftResult['updateKin'];
  removeKin: UseFounderDraftResult['removeKin'];
  set: UseFounderDraftResult['set'];
}

function Dash() {
  return <abbr title="none">—</abbr>;
}

function FounderOwnPanel({
  draft,
  set,
}: {
  draft: FounderDraft;
  set: UseFounderDraftResult['set'];
}) {
  const mother = draft.kin.find((kin) => kin.relation === 'mother');
  const father = draft.kin.find((kin) => kin.relation === 'father');
  // Gender-neutral by construction (#3983 Plan B Task 5) — `CharacterDraft`
  // (`character-creation/types.ts`) carries no name field for these
  // components to resolve a gendered "daughter of"/"son of" word from
  // either, and threading the full draft through just for that word would
  // widen this panel's dependency past the founder draft it otherwise only
  // needs. The plate's own "daughter of" is listed as an omission in the
  // task report.
  const chips = [mother, father]
    .filter((row): row is FounderKin => row != null)
    .map((row) => `child of ${row.name}`);

  return (
    <div className="panel">
      <div className="field">
        <span className="label">you are</span>
        <div className="seg" role="group" aria-label="Your place in the house">
          {FOUNDER_PLACE_CHOICES.map((choice) => (
            <button
              key={choice.value}
              type="button"
              aria-pressed={draft.founder_relation === choice.value}
              onClick={() => set('founder_relation', choice.value)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      </div>
      <div className="row3">
        <div className="field">
          <span className="label">mother</span>
          <div className="val">{mother ? mother.name : <Dash />}</div>
        </div>
        <div className="field">
          <span className="label">father</span>
          <div className="val">{father ? father.name : <Dash />}</div>
        </div>
        <div className="field">
          <span className="label">place</span>
          <div className="seg" role="group" aria-label="Place in the line">
            <button
              type="button"
              aria-pressed={draft.founder_is_heir}
              onClick={() => set('founder_is_heir', true)}
            >
              heir
            </button>
            <button
              type="button"
              aria-pressed={!draft.founder_is_heir}
              onClick={() => set('founder_is_heir', false)}
            >
              younger
            </button>
          </div>
        </div>
      </div>
      {chips.length > 0 && (
        <div className="field">
          <span className="label">on the public record</span>
          <div className="chips">
            {chips.map((chip) => (
              <span key={chip} className="chip acc">
                {chip}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function KinEditPanel({
  kin,
  updateKin,
  removeKin,
}: {
  kin: FounderKin;
  updateKin: UseFounderDraftResult['updateKin'];
  removeKin: UseFounderDraftResult['removeKin'];
}) {
  const { data: genders } = useGenders();
  const { data: houses } = useAllHouses();
  const bornIntoOptions = (houses?.results ?? []).filter(
    (house): house is typeof house & { family_id: number } => house.family_id != null
  );
  const nameId = useId();
  const ageId = useId();
  const genderId = useId();
  const bornIntoId = useId();

  return (
    <div className="panel">
      <div className="row3">
        <div className="field">
          <label htmlFor={nameId}>name</label>
          <input
            id={nameId}
            type="text"
            value={kin.name}
            onChange={(event) => updateKin(kin.key, { name: event.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor={ageId}>age</label>
          <input
            id={ageId}
            type="number"
            min={0}
            value={kin.age != null ? String(kin.age) : ''}
            onChange={(event) =>
              updateKin(kin.key, {
                age: event.target.value.trim() === '' ? null : Number(event.target.value),
              })
            }
          />
        </div>
        <div className="field">
          <label htmlFor={genderId}>gender</label>
          <select
            id={genderId}
            value={kin.gender_id != null ? String(kin.gender_id) : ''}
            onChange={(event) =>
              updateKin(kin.key, {
                gender_id: event.target.value === '' ? null : Number(event.target.value),
              })
            }
          >
            <option value="">unspecified</option>
            {(genders ?? []).map((gender) => (
              <option key={gender.id} value={String(gender.id)}>
                {gender.display_name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="row2">
        <div className="field">
          <span className="label">deceased</span>
          <div className="seg" role="group" aria-label="deceased">
            <button
              type="button"
              aria-pressed={!kin.is_deceased}
              onClick={() => updateKin(kin.key, { is_deceased: false })}
            >
              no
            </button>
            <button
              type="button"
              aria-pressed={kin.is_deceased}
              onClick={() => updateKin(kin.key, { is_deceased: true })}
            >
              yes
            </button>
          </div>
        </div>
        <div className="field">
          <label htmlFor={bornIntoId}>born into</label>
          <select
            id={bornIntoId}
            value={kin.born_into_id != null ? String(kin.born_into_id) : ''}
            onChange={(event) => {
              const value = event.target.value;
              if (value === '') {
                updateKin(kin.key, { born_into_id: null, born_into_name: '' });
                return;
              }
              const house = bornIntoOptions.find((option) => option.family_id === Number(value));
              updateKin(kin.key, {
                born_into_id: Number(value),
                born_into_name: house?.name ?? '',
              });
            }}
          >
            <option value="">the house itself</option>
            {bornIntoOptions.map((house) => (
              <option key={house.id} value={String(house.family_id)}>
                {house.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="savebar">
        <button type="button" className="btn sm" onClick={() => removeKin(kin.key)}>
          Remove
        </button>
      </div>
    </div>
  );
}

export function FounderPersonPanel({
  node,
  draft,
  keyByNodeId,
  updateKin,
  removeKin,
  set,
}: FounderPersonPanelProps) {
  if (node.id === FOUNDER_NODE_ID) {
    return <FounderOwnPanel draft={draft} set={set} />;
  }
  const key = keyByNodeId[node.id];
  const kin = draft.kin.find((row) => row.key === key);
  if (!kin) return null;
  return <KinEditPanel kin={kin} updateKin={updateKin} removeKin={removeKin} />;
}
