/**
 * FamilyChapter (#3983 Task 9, plate S-IV "The Family") — the kinship tree
 * plus the household band, with the selected person's `PersonPanel` opened
 * INSIDE their own `<li>`.
 *
 * The tree is built from `parentage` (child under parent; a node with no
 * incoming parentage edge is a root) and `unions`: a union member who never
 * appears in `parentage` at all (never a parent, never a child) is an
 * "outsider" spouse — married in, no blood tie — and renders as a sibling
 * `<li>` inside their in-line partner's own children list, labeled
 * "consort" (plate S-IV's Raffaele). A union between two blood members of
 * the tree (a cousin marriage) is left in its natural tree position with no
 * extra annotation — the plate draws only the outsider case, and this is
 * the rarer one; `union.kind` would supply the relation word for it if a
 * demo ever needs it.
 *
 * The plate's polished status words ("described"/"sheeted"/"played") don't
 * map cleanly from `AlmanachFamilyNode.tier` (the raw `DefinitionTier`
 * value, e.g. "pc"/"name_only") or any other wire field, so the status
 * column shows "deceased" when true, else the raw tier string — UNLESS the
 * row conceals something, in which case it reads "hidden truth" (plate
 * S-IV's own Marisol row), matching the `st hid` class rather than leaving
 * it text-blank (review fix round 1, Finding I1). A tree node conceals
 * something when `believed_deceased` is true OR any `parentage` edge
 * touching it (as parent or child) is `is_true: false` or `via_secret:
 * true`; a household row (no parentage edges of its own) checks only
 * `believed_deceased`. Relation words ("head of house"/"child"/
 * "grandchild") are similarly structural, not the plate's titled ranks
 * ("Grand Princess"/"heir presumptive") — no title/rank field exists on the
 * wire either.
 *
 * The plate's own `.panel` markup draws no Save button of its own (the
 * chapter-level savebar sits outside the tree instead) — `PersonPanel`
 * carries its own Save immediately under the fields it commits, since only
 * one panel is ever open at a time; there's also no top-level prose field
 * here for a chapter-wide "draft kept as you type" note to describe, so
 * this chapter renders no outer savebar at all (unlike House/Lands/Estate).
 */
import { useState, type ReactNode } from 'react';

import type { AlmanachFamily, AlmanachFamilyNode, AlmanachHouseholdMember } from '../types';
import { PersonPanel, type PersonPanelSaveFields, type PersonPanelSubject } from './PersonPanel';
import { AddKinDialog, type CreateKinFields, type KinRelation } from './AddKinDialog';

export interface FamilyChapterProps {
  houseId: number;
  houseName: string;
  family: AlmanachFamily;
  household: AlmanachHouseholdMember[];
  onEdit: (fields: PersonPanelSaveFields) => void;
  /** Optional — omitted in isolation (e.g. the unit test) disables the add doors. */
  onCreate?: (fields: CreateKinFields) => void;
  /**
   * Replaces the built-in `PersonPanel` for BOTH a selected tree node and a
   * selected household row (#3983 Plan B Task 5) — a household row is
   * repackaged as an `AlmanachFamilyNode`-shaped stand-in
   * (`nodeFromHousehold`) so the founder Almanach's `FounderPersonPanel` has
   * one override surface for both. Omitted (the default): every other
   * caller keeps the built-in `PersonPanel`/`onEdit` wiring unchanged.
   */
  renderPanel?: (node: AlmanachFamilyNode) => ReactNode;
  /** The tree's own "add a child/spouse" door label — default unchanged. */
  addLabel?: string;
  /** The household band's own add-door label — default unchanged. */
  householdAddLabel?: string;
  /** Narrows `AddKinDialog`'s relation choices (the founder dialog offers
   * only head-relative relations, never `grandparent` — see
   * `founder/familyShape.ts`). Omitted keeps `AddKinDialog`'s own default
   * (every relation). */
  relations?: KinRelation[];
  /** Forwarded to `AddKinDialog` (final review I4) — the founder chapter
   * passes `true` so a child/sibling row can be left "to be defined";
   * every staff caller omits it and keeps requiring a name. */
  allowEmptyKinName?: boolean;
  /** Forwarded to `AddKinDialog` (final review I3/deferred item 8) — the
   * founder chapter passes `false` (its submit path never reaches
   * `almanach_edit_kin`); every staff caller omits it and keeps the "of
   * whom" requirement. */
  requireRelativeAnchor?: boolean;
  /**
   * Replaces the built-in `.row3` stat fields (#3983 Plan B Task 5) — the
   * founder plate's own "family you may define"/"household" counts have no
   * relationship to this component's "on record"/"open positions"/"hidden
   * truths" trio, which stays hardcoded for every other (staff) caller.
   * Omitted keeps the built-in three fields.
   */
  row3?: ReactNode;
  /** Node id -> `.who .rel` text, overriding the structural depth-based
   * `relationLabel`/outsider-spouse "consort" this component would
   * otherwise compute (the founder tree's vocabulary is head-relative, not
   * depth-relative — see `founder/familyShape.ts`). Omitted keeps the
   * built-in structural words. */
  relationOverrides?: Record<number, string>;
  /** Node id -> `.who .st` text/class, overriding the structural
   * deceased/hidden-truth/tier status this component would otherwise
   * compute — only the founder's own row needs one ("your character",
   * `st you`). Omitted keeps the built-in status text. */
  statusOverrides?: Record<number, { text: string; className: string }>;
  /** Rendered at the end of the `<main className="chapter">` this component
   * owns, after the add-kin dialog (#3983 Plan B Task 5) — this component
   * draws no savebar of its own (see the module docstring), but the founder
   * Almanach's own chapters always need a "draft kept as you type" + Next
   * savebar, and that savebar has to sit INSIDE the same `<main>` element
   * the plate's CSS grid expects, not as a trailing sibling. Omitted keeps
   * today's no-footer shape. */
  footer?: ReactNode;
}

/** A household row, repackaged as the shape `renderPanel` takes — lets one
 * override function (keyed by node/holder id) cover both the tree and the
 * household band (#3983 Plan B Task 5). Every field `AlmanachHouseholdMember`
 * doesn't carry (tier, family_id, is_appable, sheet_id, gender, age,
 * description) reads as the same "unknown" value `PersonPanel`'s own
 * `subjectForHousehold` already falls back to. */
function nodeFromHousehold(row: AlmanachHouseholdMember): AlmanachFamilyNode {
  return {
    id: row.holder_id as number,
    name: row.holder_name,
    tier: '',
    family_id: null,
    is_deceased: row.is_deceased,
    is_appable: false,
    sheet_id: null,
    gender: '',
    age: null,
    description: '',
    believed_deceased: row.believed_deceased,
  };
}

const HIDDEN_TRUTH = 'hidden truth';

/** Whether any `parentage` edge touching `nodeId` (as parent or child) is
 * marked untrue or gated by a secret. */
function hasParentageSecret(nodeId: number, parentage: AlmanachFamily['parentage']): boolean {
  return parentage.some(
    (edge) =>
      (edge.child_id === nodeId || edge.parent_id === nodeId) && (!edge.is_true || edge.via_secret)
  );
}

function nodeStatusText(node: AlmanachFamilyNode, family: AlmanachFamily): string {
  if (node.believed_deceased || hasParentageSecret(node.id, family.parentage)) return HIDDEN_TRUTH;
  if (node.is_deceased) return 'deceased';
  return node.tier;
}

function householdStatusText(row: AlmanachHouseholdMember): string {
  if (row.believed_deceased) return HIDDEN_TRUTH;
  return row.is_deceased ? 'deceased' : 'household';
}

function relationLabel(depth: number): string {
  if (depth === 0) return 'head of house';
  if (depth === 1) return 'child';
  if (depth === 2) return 'grandchild';
  return 'descendant';
}

interface TreeIndex {
  childrenByParent: Map<number, number[]>;
  roots: AlmanachFamilyNode[];
  /** `nodeId -> [outsider spouse node, ...]` from `unions`. */
  outsiderSpousesOf: Map<number, AlmanachFamilyNode[]>;
}

/**
 * `roots`/`outsiderSpousesOf` (#3983 Plan B Task 5 fix round 1, Finding
 * I1) — a node's "outsider spouse" status is decided by whether it has an
 * INCOMING parentage edge (`childIds`), not by the old `bloodIds` (anyone
 * EVER a `parent_id` OR `child_id`). The old criterion meant a union member
 * who parents a shared child but is never anyone's own recorded child (the
 * founder's own head+spouse+child scenario — `founder/familyShape.ts`'s
 * `case 'child'` gives the founder a parentage edge to BOTH the head and
 * the head's spouse) got wrongly counted as "blood" purely for being a
 * parent, which excluded it from outsider-spouse nesting and left it as a
 * spurious second root instead. `family.nodes` order is root-line,
 * depth-first-stable order: the first union member (in that order) reaches
 * `roots`/`claimed` and becomes the anchor; every later member sharing a
 * union with an already-claimed id nests beside that partner instead of
 * ever being considered for root status itself — this also covers the
 * original "married in with zero parentage edges at all" case, since
 * having no incoming edge is a superset that includes it. A union whose
 * members ALL lack an incoming edge (e.g. a founder who IS the head, with
 * no recorded parents of her own, plus her equally parent-less spouse) has
 * nobody naturally "in line" to anchor on — the first member encountered
 * (`family.nodes` order) becomes the root and the rest nest beside them,
 * rather than dropping the union as the old code did (leaving nobody
 * placed at all).
 *
 * `renderNode` (below) separately dedupes a node reachable via more than
 * one `childrenByParent` entry (the same founder/head+spouse scenario
 * above also gives the shared child TWO parent edges) — that's the other
 * half of I1: even with the spouse correctly nested rather than rooted,
 * the child would still render once under each parent's own subtree
 * without a shared `renderedIds` guard across the whole tree walk.
 */
function buildTreeIndex(family: AlmanachFamily): TreeIndex {
  const nodeById = new Map(family.nodes.map((n) => [n.id, n]));
  const childIds = new Set(family.parentage.map((e) => e.child_id));
  const childrenByParent = new Map<number, number[]>();
  for (const edge of family.parentage) {
    const list = childrenByParent.get(edge.parent_id) ?? [];
    list.push(edge.child_id);
    childrenByParent.set(edge.parent_id, list);
  }

  const partnersOf = new Map<number, number[]>();
  for (const union of family.unions) {
    const members = union.member_ids.filter((id) => nodeById.has(id));
    for (const memberId of members) {
      const others = members.filter((id) => id !== memberId);
      const list = partnersOf.get(memberId) ?? [];
      list.push(...others);
      partnersOf.set(memberId, list);
    }
  }

  const roots: AlmanachFamilyNode[] = [];
  const outsiderSpousesOf = new Map<number, AlmanachFamilyNode[]>();
  const claimed = new Set<number>();
  // "Already placed" — will render somewhere in the tree without this
  // loop's help — means EITHER it has its own incoming parentage edge
  // (renders naturally as someone's child, via `childrenByParent`) OR this
  // same loop already claimed it (a root, or nested beside an earlier
  // partner). A node with an incoming edge is never itself added to
  // `claimed` (it's skipped outright below), so both checks are needed —
  // `childIds` alone would miss a root that claimed a partner earlier in
  // this same pass, and `claimed` alone would miss a partner who has an
  // incoming edge and so never entered this loop's `roots`/outsider logic
  // at all.
  for (const node of family.nodes) {
    if (childIds.has(node.id) || claimed.has(node.id)) continue;
    const claimedPartnerId = (partnersOf.get(node.id) ?? []).find(
      (id) => childIds.has(id) || claimed.has(id)
    );
    if (claimedPartnerId != null) {
      const list = outsiderSpousesOf.get(claimedPartnerId) ?? [];
      list.push(node);
      outsiderSpousesOf.set(claimedPartnerId, list);
    } else {
      roots.push(node);
    }
    claimed.add(node.id);
  }

  return { childrenByParent, roots, outsiderSpousesOf };
}

export function FamilyChapter({
  houseId,
  houseName,
  family,
  household,
  onEdit,
  onCreate,
  renderPanel,
  addLabel = '⊕ a child · a spouse',
  householdAddLabel = '⊕ a person of the household · a position',
  relations,
  allowEmptyKinName,
  requireRelativeAnchor,
  row3,
  relationOverrides,
  statusOverrides,
  footer,
}: FamilyChapterProps) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState<'kin' | 'household' | null>(null);
  const index = buildTreeIndex(family);

  const select = (id: number) => setSelectedId((current) => (current === id ? null : id));

  const subjectForNode = (node: AlmanachFamilyNode, relation: string): PersonPanelSubject => ({
    kinspersonId: node.id,
    name: node.name,
    tier: node.tier,
    age: node.age,
    gender: node.gender,
    isDeceased: node.is_deceased,
    believedDeceased: node.believed_deceased,
    inTheHouseAs: relation,
    bornInto: '',
    description: node.description,
  });

  const subjectForHousehold = (row: AlmanachHouseholdMember): PersonPanelSubject => ({
    kinspersonId: row.holder_id as number,
    name: row.holder_name,
    tier: '',
    age: null,
    gender: '',
    isDeceased: row.is_deceased,
    believedDeceased: row.believed_deceased,
    inTheHouseAs: `household · ${row.position}`,
    bornInto: '',
    description: '',
  });

  const nodeById = new Map(family.nodes.map((n) => [n.id, n]));

  // A node reachable through more than one `childrenByParent` entry (the
  // founder's own head+spouse+child scenario gives a child two parent
  // edges — #3983 Plan B Task 5 fix round 1, Finding I1) renders exactly
  // once, at the first encounter in this root-line depth-first walk — every
  // later attempt (from the second parent) is a no-op. One `Set` shared
  // across the whole walk, not per-call: `renderNode` recurses into both
  // `outsiders` and `childIds`, and either path can reach the same id.
  const renderedIds = new Set<number>();

  /** `relationOverride` covers the outsider-spouse case ("consort") — every
   * other caller lets `depth` supply the structural word. */
  const renderNode = (
    node: AlmanachFamilyNode,
    depth: number,
    relationOverride?: string,
    asConsort = false
  ): ReactNode => {
    if (renderedIds.has(node.id)) return null;
    renderedIds.add(node.id);
    const relation = relationOverrides?.[node.id] ?? relationOverride ?? relationLabel(depth);
    const selected = selectedId === node.id;
    // A consort rendered beside their partner never carries the union's
    // children: those hang under the partner who is in the line, so a
    // daughter is never drawn a rung below her outsider parent as a
    // "grandchild" (#3983 demo-fidelity finding 2).
    const outsiders = asConsort ? [] : (index.outsiderSpousesOf.get(node.id) ?? []);
    const childIds = asConsort ? [] : (index.childrenByParent.get(node.id) ?? []);
    const hasChildList = outsiders.length > 0 || childIds.length > 0;
    const hidden = node.believed_deceased || hasParentageSecret(node.id, family.parentage);
    const status = statusOverrides?.[node.id];
    return (
      <li key={node.id} className={selected ? 'sel' : undefined}>
        <div className="who">
          <span className={node.is_deceased ? 'nm dead' : 'nm'}>
            <button type="button" aria-expanded={selected} onClick={() => select(node.id)}>
              {node.name}
            </button>
          </span>
          <span className="rel">{relation}</span>
          <span className={status?.className ?? (hidden ? 'st hid' : 'st')}>
            {status?.text ?? nodeStatusText(node, family)}
          </span>
        </div>
        {selected &&
          (renderPanel ? (
            renderPanel(node)
          ) : (
            <PersonPanel subject={subjectForNode(node, relation)} onSave={onEdit} />
          ))}
        {hasChildList && (
          <ul>
            {outsiders.map((spouse) => renderNode(spouse, depth + 1, 'consort', true))}
            {childIds.map((childId) => {
              const childNode = nodeById.get(childId);
              return childNode ? renderNode(childNode, depth + 1) : null;
            })}
          </ul>
        )}
      </li>
    );
  };

  const openHousehold = household.filter((row) => row.is_open).length;
  const hiddenTruths =
    family.nodes.filter((n) => n.believed_deceased).length +
    household.filter((row) => row.believed_deceased).length;

  return (
    <main className="chapter">
      <h3>
        The Family <span className="tier">{houseName}</span>
      </h3>
      <div className="row3">
        {row3 ?? (
          <>
            <div className="field">
              <span className="label">on record</span>
              <div className="val">{family.nodes.length}</div>
            </div>
            <div className="field">
              <span className="label">open positions</span>
              <div className="val">{openHousehold}</div>
            </div>
            <div className="field">
              <span className="label">hidden truths</span>
              <div className="val">{hiddenTruths}</div>
            </div>
          </>
        )}
      </div>
      <ul className="tree">
        {index.roots.map((root) => renderNode(root, 0))}
        <li>
          <div className="who">
            <button type="button" className="add" onClick={() => setAddOpen('kin')}>
              {addLabel}
            </button>
          </div>
        </li>
        {household.length > 0 && (
          <>
            <li className="band">
              <span className="label">household</span>
            </li>
            {household.map((row) =>
              row.holder_id == null ? (
                <li key={row.vacancy_id}>
                  <div className="who">
                    <span className="nm">{row.position}</span>
                    <span className="rel">position</span>
                    <span className="st open">open</span>
                  </div>
                </li>
              ) : (
                <li
                  key={row.vacancy_id}
                  className={selectedId === row.holder_id ? 'sel' : undefined}
                >
                  <div className="who">
                    <span className={row.is_deceased ? 'nm dead' : 'nm'}>
                      <button
                        type="button"
                        aria-expanded={selectedId === row.holder_id}
                        onClick={() => select(row.holder_id as number)}
                      >
                        {row.holder_name}
                      </button>
                    </span>
                    <span className="rel">{row.position}</span>
                    <span className={row.believed_deceased ? 'st hid' : 'st'}>
                      {householdStatusText(row)}
                    </span>
                  </div>
                  {selectedId === row.holder_id &&
                    (renderPanel ? (
                      renderPanel(nodeFromHousehold(row))
                    ) : (
                      <PersonPanel subject={subjectForHousehold(row)} onSave={onEdit} />
                    ))}
                </li>
              )
            )}
          </>
        )}
        <li>
          <div className="who">
            <button type="button" className="add" onClick={() => setAddOpen('household')}>
              {householdAddLabel}
            </button>
          </div>
        </li>
      </ul>
      {onCreate && addOpen && (
        <AddKinDialog
          houseId={houseId}
          nodes={family.nodes}
          defaultHousehold={addOpen === 'household'}
          open={addOpen != null}
          onClose={() => setAddOpen(null)}
          onConfirm={onCreate}
          relations={relations}
          allowEmptyName={allowEmptyKinName}
          requireRelativeAnchor={requireRelativeAnchor}
        />
      )}
      {footer}
    </main>
  );
}
