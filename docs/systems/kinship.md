# Kinship (#2062)

Person-node genealogy with typed edges, a truth-vs-public-record layer, and
the app-in slot mountain. Lives in `world/roster` (models in
`models/families.py`, services in `services/kinship.py`). See ADR-0097 for
the shape rationale; succession law and house recognition consume these
facts from #1884.

## Models

- **`Family`** — surname container (noble/commoner/crime, `origin_realm`).
  Nodes are not family-owned; `Kinsperson.family` is a denorm of the active
  primary `FamilyMembership`.
- **`Kinsperson`** — a person-node at a definition tier aligned with the NPC
  ladder (`NAME_ONLY → FUNCTIONARY → STANDING → SHEETED → PC`); anchors:
  `sheet` (OneToOne CharacterSheet), `functionary`. Appable-slot fields
  (`is_appable`, `name_locked`, age band, `allowed_genders`) + CG deferral
  (`deferred_definer`). Heredity stub fields (#2815): nullable `species` FK
  and nullable `power_band` (`PowerBand` choices; null = unspecified,
  assumed sub-Puissant; staff/GM-authored only).
- **`KinspersonTraitValue`** — a pinned appearance value (kinsperson →
  `forms.FormTrait` → `forms.FormTraitOption`, unique per trait, #2815).
  Written by CG approval back-inference (a child's off-palette color is
  attributed to the cross-species parent, who acquires it) or authored by
  staff; once pinned it constrains later siblings' inherited options.
- **`FamilyMembership`** — claim rows (basis: born/married-in/adopted/
  legitimized/granted/founding; end reasons incl. disowned) — the history +
  law input.
- **`UnionKind`** (authorable vocabulary, `confers_wedlock`) + **`Union`**
  (M2M members, 2+, any composition) — in-laws and step-parents derive from
  these; births stamp `born_within_union` for legitimacy law.
- **`ParentageEdge`** — typed child→parent facts (`BIOLOGICAL /
  TREE_OF_SOULS / VAMPIRIC_EMBRACE / ADOPTIVE / FOSTER / ACKNOWLEDGED`),
  N per child. Step-parents are DERIVED, never stored. `is_ritual_invoker`
  (#2815) marks the Tree of Souls invoker — the dominant-line partner
  regardless of gender, at most one per child (partial unique constraint).
- **`Soul` + `SoulIncarnation`** — reincarnation chains with per-life
  knowledge (the Monique/Covet contract, tested literally).
- **`KinSlotPool`** — fuzzy appable capacity minting nodes on claim.

Truth trio on edges/unions/incarnations: `is_public_record`, `is_true`,
`secret` FK (→`secrets.Secret`; ADR-0010 direction). Hidden + no secret =
staff-only. `Secret.subject_aware=False` (new field) keeps subject-unaware
truths off the owner's own shelf (`secrets_owned_by` filters).

## Heredity service (`world.roster.services.heredity`, #2815)

Parent Dominance: species inheritance is magical and maternal by default.
`DOMINANCE_TIER` collapses `PowerBand` values (everything sub-Puissant,
including null, is tier 0; then Puissant < True < Grand < Transcendent).
`derive_lines_for_child(child)` builds `ParentLine`s kind-aware (gender for
BIOLOGICAL, `is_ritual_invoker` for TREE_OF_SOULS); `derivable_species`
returns the legal child species (maternal always; paternal appended when his
tier strictly exceeds hers; `chimeric_possible` when both are Grand+ and
differ); `inherited_options` returns cross-line `FormTraitOption`s per trait
(pins constrain, unpinned parents expose their species palette, own-palette
overlap excluded so hidden ancestry stays hideable); `base_trait_options`
narrows a child of fully-defined parents to the family look — when every
parent line is pinned for a trait, options collapse to the same-species
parents' pins, dominant line first (an unpinned side keeps the species
palette open). Validation built on it
is **one-directional and creation-time only** (ADR-0173): outcomes require
supporting bands when created; parents may be retro-defined upward freely.
Named "heredity" — NOT "lineage" (that word is taken three other ways).

## Services (`world.roster.services.kinship`)

Writers: `create_person`, `record_parentage` (mints subject-unaware
GM-authored Secrets for hidden edges), `record_union`,
`record_incarnation`, `add_membership`/`end_membership` (denorm
maintenance), `mint_from_pool`, `claim_appable_node` (CG bind,
constraint-checked), `ensure_node_for_sheet`, `define_deferred`
(holder-gated). Errors: `KinshipServiceError.user_message`.

Readers (all viewer-aware; `viewer` = RosterEntry, `None` = public-only,
`OMNISCIENT` sentinel = staff): `parents_of`, `children_of`, `siblings_of`
(full/half), `spouses_of`, `step_parents_of`, `unions_of`,
`incarnation_chain_of` (per-life knowledge), `derive_relationship` (labeled
precedence walk incl. foster/step/in-law/soul), `family_tree_for` (graph
payload for a `Family`), `kin_tree_for_sheet` (#3003 — the same graph payload
centred on one `CharacterSheet`: delegates to `family_tree_for` when the
sheet's `Kinsperson` node has a family, else walks parents/children/siblings/
spouses/step-parents directly so a familyless character — Misbegotten,
tarot-named — still gets an ego-centric kin graph; `FamilyTreePayload.family`
is `None` in that branch), `open_slots_for` (CG browser). `_node_dict`/
`_edge_dict`/`_union_dict` are the single node/edge/union dict-shape
definitions both tree builders share — never duplicate them.

## Surfaces

- REST: `GET /api/roster/families/` (+`has_open_positions` filter),
  `families/:id/tree/` (viewer-filtered graph payload),
  `families/:id/slots/` (slot browser). (#3003) `kin/tree/<character_id>/`
  (viewer-filtered graph payload centred on one character — delegates to
  `kin_tree_for_sheet`) and `kin/relationship/?a=&b=` (viewer-derived
  `RelationshipType` label between two characters, or `null` — delegates to
  `derive_relationship`, its first production caller). Writes go through
  services (CG finalization + staff admin) — deliberately no generic CRUD.
- CG: draft fields `claimed_kin_slot(_id)` / `claimed_kin_pool(_id)` /
  `defer_parents`; `finalize_character` → `_bind_kinship_node` (claim →
  mint → self-serve fallback). FE: `KinSlotPicker` in LineageStage.
- Telnet: `sheet/family` (alias `kin`) section — the viewer's own visible
  kin, labeled.
- Admin: Kinsperson (+parentage/membership inlines), ParentageEdge,
  KinSlotPool.

## Seeds

Cluster `kinship` (`world/seeds/kinship.py`): PLACEHOLDER ducal house with
a 3-generation tree, 2 appable slots, 1 pool, a public-false/hidden-true
parentage pair, and a 2-life soul chain.

## Consumers / futures

#1884 houses: recognition rules + succession law query these facts
(parentage kinds, `born_within_union`, memberships). #1985 estates. Dream
sequences as past lives: designed hook on TEMPORARY personas/forms.
