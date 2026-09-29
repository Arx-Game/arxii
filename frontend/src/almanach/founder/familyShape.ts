/**
 * founderFamilyShape (#3983 Plan B Task 5) — turns the founder's own
 * localStorage draft (`FounderDraft.kin`, `founder_relation`,
 * `founder_is_heir`) into the same `AlmanachFamily`/`AlmanachHouseholdMember`
 * shapes the staff `FamilyChapter` tree already knows how to render
 * (`buildTreeIndex`, `document/FamilyChapter.tsx`), so plate F-III's tree
 * reuses that component rather than a second tree renderer.
 *
 * Every `FounderKin.relation` is HEAD-RELATIVE (mirrors
 * `world.societies.houses.constants.ClaimKinRelation`): MOTHER/FATHER are
 * the head's own parents, SPOUSE is the head's spouse, SIBLING is a child of
 * the head's own parents, CHILD is a child of the head (and of the head's
 * spouse when one is on record), GRANDPARENT is a parent of whichever of
 * MOTHER/FATHER is on record (MOTHER preferred). The founder herself is
 * placed the identical way, via `draft.founder_relation` — including
 * `'head'`, which means the founder IS the head (no separate head kin row
 * exists then). "At most one head" is enforced by the caller, not this
 * module: `FounderFamilyChapter.tsx` computes the `relations` list
 * `AddKinDialog` offers per render, dropping `'head'` once
 * `draft.founder_relation === 'head'` or `draft.kin` already carries a
 * `head` row (#3983 Plan B Task 5 fix round 1, Finding C1) — this function
 * has no opinion on it and will happily build a (malformed) shape from a
 * draft that violates the rule, same as it does for any other caller
 * mistake.
 *
 * Ids are synthetic and negative so they never collide with a real
 * `Kinsperson` pk once the claim is actually filed (Task 6): the head
 * (`HEAD_NODE_ID`, -1) and the founder (`FOUNDER_NODE_ID`, -2) are fixed;
 * every other kin row gets the next id counting down from -3, in
 * `draft.kin` order. `keyByNodeId` maps each of those synthetic ids back to
 * the `FounderKin.key` a caller needs for `updateKin`/`removeKin` — the head
 * and founder is aren't reversible that way (the founder has no `FounderKin`
 * row of her own, and the head's, when one exists, is included like any
 * other kin row).
 */
import type { KinRelation } from '../document/AddKinDialog';
import type { AlmanachFamily, AlmanachFamilyNode, AlmanachHouseholdMember } from '../types';
import type { FounderDraft, FounderKin } from './founderDraft';

/** Every relation the founder Family dialog offers (#3983 Plan B's ruling):
 * head-relative kin, plus the household band's ward/position. Never
 * `grandparent` — the backend cannot say which side of the family an
 * unattached grandparent belongs to (see this module's own docstring). */
export const FOUNDER_KIN_RELATIONS: KinRelation[] = [
  'head',
  'mother',
  'father',
  'spouse',
  'sibling',
  'child',
  'ward',
  'position',
];

/** Head-relative relation words (plate F-III's tree rows, plate F-VI's "the
 * family" line — `FounderFamilyChapter`'s `relationOverrides` and
 * `FounderRecord`'s own family line both read this same map, so neither
 * ever drifts from the other). `KinRelation` and `ClaimKinRelation`
 * (`@/character-creation/types`) are the identical nine-member union under
 * two names — this file already imports the former for
 * `FOUNDER_KIN_RELATIONS`, so it keys off that rather than adding a second
 * import of the same shape. */
export const RELATION_WORDS: Record<KinRelation, string> = {
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

/** The head-of-house tree node's synthetic id, when a separate head kin row
 * is on record (absent — `null` — when `founder_relation === 'head'`). */
export const HEAD_NODE_ID = -1;

/** The founder's own tree node — always present, always this id. */
export const FOUNDER_NODE_ID = -2;

type ParentageEdge = AlmanachFamily['parentage'][number];
type UnionEdge = AlmanachFamily['unions'][number];

function kinNode(id: number, kin: FounderKin): AlmanachFamilyNode {
  return {
    id,
    name: kin.name,
    // A founder-authored kin has never been played and carries no roster
    // entry — DefinitionTier.NAME_ONLY (`world/roster/constants.py`) is the
    // real value this row will carry once the claim is actually filed.
    tier: 'name_only',
    family_id: kin.born_into_id,
    is_deceased: kin.is_deceased,
    is_appable: false,
    sheet_id: null,
    gender: '',
    age: kin.age,
    description: '',
    believed_deceased: false,
  };
}

function parentEdge(childId: number, parentId: number): ParentageEdge {
  return {
    child_id: childId,
    parent_id: parentId,
    kind: 'biological',
    is_true: true,
    via_secret: false,
  };
}

function unionEdge(id: number, memberIds: number[]): UnionEdge {
  return { id, kind: 'marriage', member_ids: memberIds, ended: false };
}

export interface FounderFamilyShape {
  family: AlmanachFamily;
  household: AlmanachHouseholdMember[];
  /** Synthetic node id -> the `FounderKin.key` it came from. Never carries
   * `HEAD_NODE_ID`'s own entry twice, and never carries `FOUNDER_NODE_ID` at
   * all — the founder has no `FounderKin` row. */
  keyByNodeId: Record<number, string>;
}

/**
 * Builds the founder's family tree + household band from the draft, and the
 * founder's own node (named `youName`, tier `pc`).
 */
function householdMember(id: number, kin: FounderKin): AlmanachHouseholdMember {
  if (kin.relation === 'ward') {
    return {
      vacancy_id: id,
      position: 'ward',
      holder_id: id,
      holder_name: kin.name,
      is_open: false,
      count_remaining: 0,
      is_deceased: kin.is_deceased,
      believed_deceased: false,
    };
  }
  return {
    vacancy_id: id,
    position: kin.name,
    holder_id: null,
    holder_name: '',
    is_open: true,
    count_remaining: 1,
    is_deceased: false,
    believed_deceased: false,
  };
}

function addKinRelations(
  kin: FounderKin,
  id: number,
  effectiveHeadId: number | null,
  mother: { id: number; kin: FounderKin } | null,
  father: { id: number; kin: FounderKin } | null,
  spouse: { id: number; kin: FounderKin } | null,
  parentage: ParentageEdge[],
  unions: UnionEdge[]
): void {
  switch (kin.relation) {
    case 'mother':
    case 'father':
      if (effectiveHeadId != null) parentage.push(parentEdge(effectiveHeadId, id));
      return;
    case 'spouse':
      if (effectiveHeadId != null) unions.push(unionEdge(id, [effectiveHeadId, id]));
      return;
    case 'sibling':
      if (mother) parentage.push(parentEdge(id, mother.id));
      if (father) parentage.push(parentEdge(id, father.id));
      return;
    case 'child':
      if (effectiveHeadId != null) parentage.push(parentEdge(id, effectiveHeadId));
      if (spouse) parentage.push(parentEdge(id, spouse.id));
      return;
    case 'grandparent': {
      const attachTo = mother ?? father;
      if (attachTo) parentage.push(parentEdge(attachTo.id, id));
      return;
    }
    case 'head':
    case 'ward':
    case 'position':
      return;
  }
}

function addFounderRelations(
  relation: FounderDraft['founder_relation'],
  head: { id: number; kin: FounderKin } | null,
  mother: { id: number; kin: FounderKin } | null,
  father: { id: number; kin: FounderKin } | null,
  spouse: { id: number; kin: FounderKin } | null,
  parentage: ParentageEdge[],
  unions: UnionEdge[]
): void {
  switch (relation) {
    case 'mother':
    case 'father':
      if (head) parentage.push(parentEdge(head.id, FOUNDER_NODE_ID));
      return;
    case 'spouse':
      if (head) unions.push(unionEdge(FOUNDER_NODE_ID, [head.id, FOUNDER_NODE_ID]));
      return;
    case 'sibling':
      if (mother) parentage.push(parentEdge(FOUNDER_NODE_ID, mother.id));
      if (father) parentage.push(parentEdge(FOUNDER_NODE_ID, father.id));
      return;
    case 'child':
      if (head) parentage.push(parentEdge(FOUNDER_NODE_ID, head.id));
      if (spouse) parentage.push(parentEdge(FOUNDER_NODE_ID, spouse.id));
      return;
    case 'grandparent': {
      const attachTo = mother ?? father;
      if (attachTo) parentage.push(parentEdge(attachTo.id, FOUNDER_NODE_ID));
      return;
    }
    case 'head':
    default:
      return;
  }
}

/**
 * Builds the founder's family tree + household band from the draft, and the
 * founder's own node (named `youName`, tier `pc`).
 */
export function founderFamilyShape(draft: FounderDraft, youName: string): FounderFamilyShape {
  const nodes: AlmanachFamilyNode[] = [];
  const parentage: ParentageEdge[] = [];
  const unions: UnionEdge[] = [];
  const household: AlmanachHouseholdMember[] = [];
  const keyByNodeId: Record<number, string> = {};
  const idByKey = new Map<string, number>();
  let nextId = -3;
  for (const kin of draft.kin) {
    const id = kin.relation === 'head' ? HEAD_NODE_ID : nextId--;
    idByKey.set(kin.key, id);
    keyByNodeId[id] = kin.key;
  }
  const firstOf = (relation: FounderKin['relation']) => {
    const kin = draft.kin.find((candidate) => candidate.relation === relation);
    if (!kin) return null;
    const id = idByKey.get(kin.key);
    return id == null ? null : { id, kin };
  };
  const head = firstOf('head');
  const mother = firstOf('mother');
  const father = firstOf('father');
  const spouse = firstOf('spouse');
  const effectiveHeadId = head?.id ?? (draft.founder_relation === 'head' ? FOUNDER_NODE_ID : null);

  for (const kin of draft.kin) {
    const id = idByKey.get(kin.key);
    if (id == null) continue;
    if (kin.is_household) {
      household.push(householdMember(id, kin));
      continue;
    }
    nodes.push(kinNode(id, kin));
    addKinRelations(kin, id, effectiveHeadId, mother, father, spouse, parentage, unions);
  }

  nodes.push({
    id: FOUNDER_NODE_ID,
    name: youName,
    tier: 'pc',
    family_id: null,
    is_deceased: false,
    is_appable: true,
    sheet_id: null,
    gender: '',
    age: null,
    description: '',
    believed_deceased: false,
  });
  addFounderRelations(draft.founder_relation, head, mother, father, spouse, parentage, unions);
  return { family: { nodes, parentage, unions }, household, keyByNodeId };
}
