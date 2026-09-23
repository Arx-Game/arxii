/**
 * FounderFamilyChapter (#3983 Plan B Task 5, plate F-III "The Family") — the
 * founder's own kin tree, built from `founderFamilyShape` and rendered
 * through the shared `document/FamilyChapter` (its tree/household-band
 * markup, `AddKinDialog` wiring, and `PersonPanel` slot swapped for
 * `FounderPersonPanel` via `renderPanel`). Head-relative relation words
 * ("head of house"/"mother"/"consort"/…) and the founder's own status
 * ("your character") don't fall out of `FamilyChapter`'s own structural,
 * depth-based vocabulary, so this chapter supplies `relationOverrides`/
 * `statusOverrides` keyed by `founderFamilyShape`'s synthetic node ids
 * rather than re-deriving a second tree renderer.
 *
 * `AddKinDialog`'s relation picker is narrowed to the head-relative set the
 * founder dialog actually offers (never `grandparent` — the backend cannot
 * tell which side of the family an unattached grandparent belongs to; see
 * `familyShape.ts`'s own docstring and #3983 Plan B's ruling).
 */
import { useMemo } from 'react';

import type { CreateKinFields } from '../document/AddKinDialog';
import { FamilyChapter } from '../document/FamilyChapter';
import { DRAFT_NOTE } from '../copy';
import { useAllHouses } from '../queries';
import type { ClaimKinRelation } from '@/character-creation/types';
import type { HouseTemplateOption } from '@/character-creation/api';

import { founderFamilyShape, FOUNDER_KIN_RELATIONS, FOUNDER_NODE_ID } from './familyShape';
import { FounderPersonPanel } from './FounderPersonPanel';
import type { FounderDraft, UseFounderDraftResult } from './founderDraft';

const RELATION_WORDS: Record<ClaimKinRelation, string> = {
  head: 'head of house',
  mother: 'mother',
  father: 'father',
  spouse: 'consort',
  sibling: 'sibling',
  child: 'child',
  grandparent: 'grandparent',
  ward: 'ward',
  position: 'position',
};

function Dash() {
  return <abbr title="none">—</abbr>;
}

export interface FounderFamilyChapterProps {
  draft: FounderDraft;
  set: UseFounderDraftResult['set'];
  addKin: UseFounderDraftResult['addKin'];
  updateKin: UseFounderDraftResult['updateKin'];
  removeKin: UseFounderDraftResult['removeKin'];
  template: HouseTemplateOption;
  youName: string;
  onNext: () => void;
}

export function FounderFamilyChapter({
  draft,
  set,
  addKin,
  updateKin,
  removeKin,
  template,
  youName,
  onNext,
}: FounderFamilyChapterProps) {
  const { data: houses } = useAllHouses();
  const shape = useMemo(() => founderFamilyShape(draft, youName), [draft, youName]);

  const relationOverrides: Record<number, string> = {
    [FOUNDER_NODE_ID]: draft.founder_is_heir ? 'heir' : 'younger',
  };
  for (const [idText, key] of Object.entries(shape.keyByNodeId)) {
    const kin = draft.kin.find((row) => row.key === key);
    if (!kin || kin.is_household) continue;
    const word = RELATION_WORDS[kin.relation];
    relationOverrides[Number(idText)] =
      kin.relation === 'spouse' && kin.born_into_name !== ''
        ? `${word} · born ${kin.born_into_name}`
        : word;
  }

  const statusOverrides = {
    [FOUNDER_NODE_ID]: { text: 'your character', className: 'st you' },
  };

  const handleCreate = (fields: CreateKinFields) => {
    const bornIntoName =
      fields.born_into_family_id != null
        ? ((houses?.results ?? []).find((house) => house.family_id === fields.born_into_family_id)
            ?.name ?? '')
        : '';
    addKin({
      name: fields.name,
      relation: fields.relation,
      gender_id: fields.gender_id ?? null,
      age: fields.age ?? null,
      is_deceased: fields.is_deceased ?? false,
      born_into_id: fields.born_into_family_id ?? null,
      born_into_name: bornIntoName,
      is_household: fields.is_household ?? false,
    });
  };

  // `HouseTemplateOption` (`src/generated/api.d.ts`, Task 3's regen) has no
  // `starting_kin_slots` field yet — the narrowed read below is forward
  // provisioning for when it lands, not a claim that it exists today; see
  // the task report's findings.
  const startingSlots = (template as { starting_kin_slots?: number }).starting_kin_slots;
  const namedCount = draft.kin.filter((kin) => !kin.is_household).length;
  const familyDefineText =
    startingSlots != null ? `${startingSlots} · ${namedCount} named` : String(namedCount);
  const onRecord = namedCount + 1;
  const householdCount = shape.household.length;

  const row3 = (
    <>
      <div className="field">
        <span className="label">family you may define</span>
        <div className="val">{familyDefineText}</div>
      </div>
      <div className="field">
        <span className="label">on record</span>
        <div className="val">{onRecord}</div>
      </div>
      <div className="field">
        <span className="label">household</span>
        <div className="val">{householdCount > 0 ? householdCount : <Dash />}</div>
      </div>
    </>
  );

  return (
    <FamilyChapter
      // The founder has no real house org yet — `AddKinDialog` (through
      // `FamilyChapter`) sends `org_id: 0` for this placeholder;
      // `handleCreate` above maps its payload into a `FounderKin` before it
      // ever reaches the draft, so the placeholder id never leaves the
      // browser (see `AddKinDialog`'s own `houseId?` doc comment).
      houseId={0}
      houseName={draft.house_name}
      family={shape.family}
      household={shape.household}
      // `renderPanel` fully replaces the built-in `PersonPanel`/`onEdit`
      // pairing for both the tree and the household band (`FamilyChapter`'s
      // own `nodeFromHousehold` repackaging) — this is never called.
      onEdit={() => {}}
      onCreate={handleCreate}
      renderPanel={(node) => (
        <FounderPersonPanel
          node={node}
          draft={draft}
          keyByNodeId={shape.keyByNodeId}
          updateKin={updateKin}
          removeKin={removeKin}
          set={set}
        />
      )}
      addLabel="⊕ a sibling · a spouse"
      householdAddLabel="⊕ a ward · a captain of the guard · a position"
      relations={FOUNDER_KIN_RELATIONS}
      row3={row3}
      relationOverrides={relationOverrides}
      statusOverrides={statusOverrides}
      footer={
        <div className="savebar">
          <span className="note">{DRAFT_NOTE}</span>
          <button type="button" className="btn" onClick={onNext}>
            Next
          </button>
        </div>
      }
    />
  );
}
