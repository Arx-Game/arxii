/**
 * PersonPanel (#3983 Task 9, plate S-IV) — the selected person's panel,
 * rendered INSIDE their `<li>` by `FamilyChapter`. Editable fields are
 * exactly `almanach_edit_kin`'s update-only "plain fields"
 * (name/gender_id/age/is_deceased/believed_deceased, `almanach.py`'s
 * `AlmanachEditKinAction.execute`) — that action applies present-only
 * (Task 10 fix; corrected here, M5): an absent kwarg is a no-op, so Save
 * still resends every field it tracks (this panel keeps no per-field dirty
 * state) but never touches `name`, which has no field of its own here (the
 * plate never draws one — the person's name is already the selection
 * button's own label).
 *
 * `tier`, `in the house as`, `born into`, `description` are read-only: no
 * kwarg on the action can change them. `in truth` stays read-only for a
 * second reason too — the document payload never carries secret text
 * (`AlmanachFamilyNode` has no field for it), so it renders a dash.
 * `public record` (final review I8) is the one field the payload DOES carry
 * a control for: a living/believed-dead seg writing `believed_deceased`
 * through the same Save as `deceased`/age/gender — the "known to the world
 * as" chip below it mirrors the seg's own live (unsaved) state, not
 * `subject.believedDeceased`, so toggling previews immediately.
 *
 * Plain `<input>`/`<select>` rather than the shadcn form primitives — this
 * panel lives in the page body, not a `Dialog`, and every other editable
 * page-body control in this feature (`LadderTable`, `LevelBar`,
 * `AlmanachPage`'s savebar) is a bare styled element; shadcn `Input`/
 * `Select` stay reserved for actual dialog popups (`PlantRungDialog`,
 * `BatchUnclaimedDialog`).
 */
import { useEffect, useId, useState } from 'react';

import { useGenders } from '../queries';

/** A tree node or a household holder, normalized to the one shape the panel
 * needs — `FamilyChapter` builds this from `AlmanachFamilyNode` or
 * `AlmanachHouseholdMember` depending on which list the selection came from. */
export interface PersonPanelSubject {
  kinspersonId: number;
  name: string;
  /** `''` when unknown (a pure household holder isn't a family tree node). */
  tier: string;
  age: number | null;
  /** Display name, e.g. "Woman" — `''` when unset. */
  gender: string;
  isDeceased: boolean;
  believedDeceased: boolean;
  /** The tree-position or household-position label ("head of house",
   * "consort", "household · ward", ...). */
  inTheHouseAs: string;
  /** `''` when not derivable from the payload. */
  bornInto: string;
  /** `''` for a household-only holder (not on `AlmanachHouseholdMember`). */
  description: string;
}

export interface PersonPanelSaveFields {
  kinsperson_id: number;
  name: string;
  age: number | null;
  gender_id: number | null;
  is_deceased: boolean;
  believed_deceased: boolean;
}

export interface PersonPanelProps {
  subject: PersonPanelSubject;
  onSave: (fields: PersonPanelSaveFields) => void;
}

function Dash() {
  return <abbr title="none">—</abbr>;
}

export function PersonPanel({ subject, onSave }: PersonPanelProps) {
  const { data: genders } = useGenders();
  const [age, setAge] = useState(subject.age != null ? String(subject.age) : '');
  const [genderId, setGenderId] = useState('');
  const [isDeceased, setIsDeceased] = useState(subject.isDeceased);
  const [believedDeceased, setBelievedDeceased] = useState(subject.believedDeceased);
  const ageInputId = useId();
  const genderSelectId = useId();

  // A fresh selection re-seeds every field from that person's own data — an
  // in-progress edit on the previously selected person must never bleed
  // into the next one.
  useEffect(() => {
    setAge(subject.age != null ? String(subject.age) : '');
    setIsDeceased(subject.isDeceased);
    setBelievedDeceased(subject.believedDeceased);
  }, [subject.kinspersonId, subject.age, subject.isDeceased, subject.believedDeceased]);

  useEffect(() => {
    const needle = subject.gender.trim().toLowerCase();
    const match =
      needle === ''
        ? undefined
        : genders?.find(
            (g) => g.display_name.toLowerCase() === needle || g.key.toLowerCase() === needle
          );
    setGenderId(match ? String(match.id) : '');
  }, [genders, subject.gender, subject.kinspersonId]);

  const submit = () => {
    onSave({
      kinsperson_id: subject.kinspersonId,
      name: subject.name,
      age: age.trim() === '' ? null : Number(age),
      gender_id: genderId === '' ? null : Number(genderId),
      is_deceased: isDeceased,
      believed_deceased: believedDeceased,
    });
  };

  return (
    <div className="panel">
      <div className="row3">
        <div className="field">
          <span className="label">tier</span>
          <div className="val">{subject.tier !== '' ? subject.tier : <Dash />}</div>
        </div>
        <div className="field">
          <label htmlFor={ageInputId}>age</label>
          <input
            id={ageInputId}
            type="number"
            min={0}
            value={age}
            onChange={(event) => setAge(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={genderSelectId}>gender</label>
          <select
            id={genderSelectId}
            value={genderId}
            onChange={(event) => setGenderId(event.target.value)}
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
      <div className="row3">
        <div className="field">
          <span className="label">deceased</span>
          <div className="seg" role="group" aria-label="deceased">
            <button type="button" aria-pressed={!isDeceased} onClick={() => setIsDeceased(false)}>
              no
            </button>
            <button type="button" aria-pressed={isDeceased} onClick={() => setIsDeceased(true)}>
              yes
            </button>
          </div>
        </div>
        <div className="field">
          <span className="label">in the house as</span>
          <div className="val">{subject.inTheHouseAs !== '' ? subject.inTheHouseAs : <Dash />}</div>
        </div>
        <div className="field">
          <span className="label">born into</span>
          <div className="val">{subject.bornInto !== '' ? subject.bornInto : <Dash />}</div>
        </div>
      </div>
      <div className="row3">
        <div className="field">
          <span className="label">public record</span>
          <div className="seg" role="group" aria-label="public record">
            <button
              type="button"
              aria-pressed={!believedDeceased}
              onClick={() => setBelievedDeceased(false)}
            >
              living
            </button>
            <button
              type="button"
              aria-pressed={believedDeceased}
              onClick={() => setBelievedDeceased(true)}
            >
              believed dead
            </button>
          </div>
        </div>
        <div className="field">
          <span className="label">in truth</span>
          <div className="val" aria-label="in truth">
            <Dash />
          </div>
        </div>
        <div className="field">
          <span className="label">known to the world as</span>
          <div className="val" aria-label="known to the world as">
            <Dash />
            {believedDeceased && <span className="chip">believed dead</span>}
          </div>
        </div>
      </div>
      <div className="field">
        <span className="label">description</span>
        <div className={subject.description === '' ? 'prose empty' : 'prose'}>
          {subject.description === '' ? 'PLACEHOLDER' : subject.description}
        </div>
      </div>
      <div className="savebar">
        <button type="button" className="btn sm" onClick={submit}>
          Save
        </button>
      </div>
    </div>
  );
}
