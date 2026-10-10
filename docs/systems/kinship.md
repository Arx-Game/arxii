# Kinship (#2062)

Person-node genealogy with typed edges, a truth-vs-public-record layer, and
the app-in slot mountain. Lives in `world/roster` (models in
`models/families.py`, services in `services/kinship.py`). See ADR-0097 for
the shape rationale; succession law and house recognition consume these
facts from #1884.

## Models

- **`Family`**: surname container (`kind` FK `FamilyKind`, `influence`,
  `origin_realm`). Nodes are not family-owned; `Kinsperson.family` is a denorm
  of the active primary `FamilyMembership`.
- **`FamilyKind`** (#3617): an authored kind of family (Commoner, Noble,
  Crime, or any kind staff add): rows, not a code list. `styles_as_house` is
  the one behaviour code reads (`world.societies.houses`). Canonical rows come
  from migration 0219 in a real deploy; test tiers never replay migration
  `RunPython`, so callers that need a canonical kind without assuming a
  migrated database call `world.roster.seeds.ensure_family_kinds()` (tests use
  `FamilyKindFactory` instead). `Family.influence` (0 = holds no authority; a
  player-named family is always 0) prices claim-path Upbringing choices; see
  `docs/systems/family-authoring-recipes.md`.
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

**`believed_deceased`** (`Kinsperson.believed_deceased`, #3983) is the same
public-record-vs-truth principle applied to one person-level fact — a death —
rather than an edge/union/incarnation, so it rides its own boolean instead of
the `is_public_record`/`is_true` pair: `is_deceased` is the private truth,
`believed_deceased` is what the world believes, independently settable. Set
only by `world.societies.houses.almanach.record_public_belief`; renders as
"hidden truth" on the Almanach's family tree wherever it (or a touching
parentage secret) makes a row's public face diverge from what actually
happened. See ADR-0312.

**Reading it is viewer-gated like every other kinship fact** (`_node_dict`,
#3983): an ordinary viewer's tree node reports
`is_deceased = is_deceased or believed_deceased` and carries no
`believed_deceased` key at all — shipping the flag beside the truth would
hand any client the very fact it hides — while the `OMNISCIENT` sentinel
(staff, the Almanach's staff-only house document) gets both raw. A house that
puts it about that its heir died is therefore not contradicted by its own
public tree.

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
payload for a `Family`: every active member, their union partners, and
since #4209 every visible parent and child of a member, so a relative who is
not of the name sits on the roll; each hop is viewer-filtered, and the
payload also carries `house`, the Organization rooted in the family, and
`realm_name`, the house's realm else the family's `origin_realm`),
`kin_tree_for_sheet` (#3003 — the same graph payload
centred on one `CharacterSheet`: delegates to `family_tree_for` when the
sheet's `Kinsperson` node has a family, else walks parents/children/siblings/
spouses/step-parents directly so a familyless character — Misbegotten,
tarot-named — still gets an ego-centric kin graph; `FamilyTreePayload.family`
is `None` in that branch), `open_slots_for` (CG browser; nothing for a
family with `is_playable=False`, since a seat CG cannot offer is not open).
`_node_dict`/`_edge_dict`/`_union_dict` are the single node/edge/union
dict-shape definitions both tree builders share — never duplicate them. The
per-tree batches (`_roster_entries_by_sheet`, `_tree_names`,
`_visible_unions_among`) run once in `_fill_payload`, so a tree's query
count does not grow with its size (asserted by
`FamilyTreeViewTests.test_query_count_does_not_grow_with_the_roll`). Each
node carries two display names (#4209): `full_name`, the full-formal
composed name (`full_display_name`, ADR-0218), and `short_name`, the tree
form, both from `world.societies.houses.services.tree_names_for`, which
composes the same grammar as `full_display_name` over facts fetched once per
tree. The tree form is relative to the family whose tree it is: a person of
that family prints the first name alone, plus `ne <BirthFamily>` when taken
in and born elsewhere; anyone else prints the common degree (first +
particle + their own family); a familyless person keeps the bare node name.
It is not a `NameDegree`, since the rule depends on the page, not the
person.

## Surfaces

- REST: `GET /api/roster/families/` (+`has_open_kin_slots` and `area_id`
  filters (renamed from `has_open_positions`, #3648), `area_id` resolves through
  `StartingArea.realm`, matching
  families with that realm or with no `origin_realm` at all),
  `families/:id/tree/` (viewer-filtered graph payload; since #4209 the
  family page's read, so it reaches every family, not only `is_playable`
  ones, which only the list filters on for CG; the payload carries `house`
  through `OrganizationShopWindowSerializer`, the realm hub's gate shape, or
  null for a family with no org, plus `realm_name`, and each node's
  `full_name`/`short_name`),
  `families/:id/slots/` (slot browser; `[]` for a non-playable family). The
  same `FamilyViewSet` is also
  mounted at `GET /api/character-creation/families/` (`character_creation/
  urls.py:38`) for the CG Lineage stage, producing two operation ids for one
  ViewSet. The list serializes from two batched groupings passed through
  serializer context - `_inherited_by_family` (#3648) and
  `houses.services.particles_for_families` (#3654, three flat queries where
  the per-row `resolve_particle` cost about six per housed family); nested
  single-object use of `FamilySerializer` still takes the per-object path.
  (#3003) `kin/tree/<character_id>/`
  (viewer-filtered graph payload centred on one character — delegates to
  `kin_tree_for_sheet`) and `kin/relationship/?a=&b=` (viewer-derived
  `RelationshipType` label between two characters, or `null` — delegates to
  `derive_relationship`, its first production caller). Writes go through
  services (CG finalization + staff admin) — deliberately no generic CRUD.
- CG: draft fields `claimed_kin_slot(_id)` / `claimed_kin_pool(_id)` /
  `defer_parents`; `finalize_character` → `_bind_kinship_node` (claim →
  mint → self-serve fallback). FE: `KinSlotPicker` in LineageStage.
- (#3003) FE: `frontend/src/kinship/components/KinshipPanel.tsx` — a Kinship
  tab on the character sheet, rendering the family tree via `KinTreeGraph`
  and the pairwise relationship label for the selected node. Each node dict
  in the tree payload (`_node_dict`) carries `sheet_id` (the bound
  `CharacterSheet` pk, or `null` when the node is unsheeted) — a distinct id
  space from the `Kinsperson` pk used for `id`, needed so the panel can call
  `kin/relationship/?a=&b=` without conflating the two. (#4210) A node also
  carries `roster_entry_id` (the `RosterEntry` pk, or `null` for an unsheeted
  node or a sheet with no entry): a third id space, the one the sheet route
  `/characters/:id` takes, batched by `_roster_entries_by_sheet` in one query
  per tree. The panel links a selected sheeted node to its sheet through it,
  reads the family line as "House X" only for a `styles_as_house` kind, and
  draws `Family.description` under that line when it is non-empty.
- (#4209) FE: the family page, `frontend/src/kinship/pages/FamilyPage.tsx`
  at `/families/:id` (a `Family` pk, never an `Organization` pk; signed-in
  viewers, the tree endpoint's own gate), over `useFamilyTree` and
  `useFamilySlots` (`kinship/queries.ts`). Sections render or vanish: the
  gate (a plate for a `styles_as_house` kind with the house's words, colours
  and sigil; a plain head otherwise), `Family.description`, the roll grouped
  by generation (`kinship/generations.ts`, the walk the graph lays out by)
  in `full_name` with a dagger for the deceased and a link for every played
  person, the tree (`KinTreeGraph`, in `short_name`), the selected person
  (full name, the kin row's blurb, and "Related as X." only when the
  relationship endpoint returns a label for the viewer's own selected
  character, `account.selected_entry.character_id`), and the open seats
  from `families/:id/slots/`. No definition tier appears on any player kin
  surface (ADR-4209): the sheet's Kin block prints `full_name` with no tier
  aside, and the graph prints `short_name` with a played person's name as
  the link to their sheet while the box selects. The sheet's House row, the
  org page's house block (`HouseDetail.family_id`) and the realm hub
  (`OrganizationShopWindow.family_id`, family-rooted orgs only) link here;
  `urls.family(id)` in `frontend/src/utils/urls.ts` is the one spelling.
- Telnet: `sheet/family` (alias `kin`) section — the viewer's own visible
  kin, labeled.
- Admin: Kinsperson (+parentage/membership inlines), ParentageEdge,
  KinSlotPool. (#4213) Family carries its kin and its slot pools as inlines
  (an appable row with no sheet is an open slot) and a read-only link to the
  Almanach house document when an organization is rooted in it; a kin row
  added on the family page is created through `create_person`, so the
  `FamilyMembership` the tree builders read exists (`Kinsperson.family` alone
  is the denorm). Rows cannot be deleted from the family page: leaving a
  family is a membership end on the person's page.

## Seeds

Cluster `kinship` (`world/seeds/kinship.py`): PLACEHOLDER ducal house with
a 3-generation tree, 2 appable slots, 1 pool, a public-false/hidden-true
parentage pair, and a 2-life soul chain.

## Consumers / futures

**The Almanach's household band is NOT a kinship concept (#3983).** A house's staff/service-
placed retainers (Ward, Household guard, ...) are a societies-side `Vacancy` band at the org's own
`Household` `OrganizationRank` — no `FamilyMembership`, no `kin_node`/`kin_pool` link, no presence
on this app's models at all. Only `believed_deceased` (above) is a real `Kinsperson` field the
Almanach writes; see `docs/systems/houses.md`'s Almanach de Catenys section for the household
mechanism itself.

#1884 houses: recognition rules + succession law query these facts
(parentage kinds, `born_within_union`, memberships). #1985 estates. Dream
sequences as past lives: designed hook on TEMPORARY personas/forms.
#3648 Vacancies: a kin Vacancy links a `KinSlotPool` or appable `Kinsperson` and
supplies the CG kin claim; #3620 (owner-defined slots) stays open.
