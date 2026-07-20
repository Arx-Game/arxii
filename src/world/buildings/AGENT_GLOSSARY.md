# Buildings glossary

Domain-local vocabulary for `world.buildings` (permits, construction, the Room
Builder #670, polish/renown-from-dwellings). Root terms live in
`AGENT_GLOSSARY_MAP.md`.

- **Space budget** — the total pool of room-size units a Building can hold
  (`Building.space_budget`), snapshotted from `BuildingSizeTier[target_size]`
  at construction and grown by a Building Extension. Rooms spend from it; it is
  NOT a room count. _Avoid:_ max rooms, room cap, room budget.
- **Fortification level** — `Building.fortification_level` (#1713): a persistent
  defense investment, raised via a `FORTIFICATION_UPGRADE` Project
  (`world.buildings.fortification_services.start_fortification_upgrade` /
  `complete_fortification_upgrade`, monotonic max-set on completion — never
  regresses), capped at `MAX_FORTIFICATION_LEVEL`. Consumed by
  `world.battles.services.create_fortification`, which snapshots it once into a
  battle-scoped `Fortification`'s `max_integrity` when that Fortification is tied
  to this Building. **Distinct from `BuildingKind.is_fortified`** — that's a
  cosmetic/filter flag on the *catalog* (one of nine non-exclusive descriptive
  tags a `BuildingKind` may carry, e.g. for search/flavor), carrying no numeric
  value and no mechanical weight; `fortification_level` is the numeric, ladder-
  gated, upgradeable defense investment on a concrete `Building` instance. A
  building can be `is_fortified=True` at `fortification_level=0`, or vice versa —
  the two are orthogonal. _Avoid:_ fortified (ambiguous between the two;
  prefer "fortification level" for the numeric investment, "is_fortified" only
  when specifically meaning the catalog tag).
- **Room size tier** — a rung on the shared unit ladder
  (`evennia_extensions.RoomSizeTier`, Micro → Expanse) giving a room its
  mechanical size (`RoomProfile.size`). The same ladder is the contract for the
  future creature-size stat (entry gating, combat range). _Avoid:_ room scale,
  footprint.
- **Dig** — the stub-creation verb of the Room Builder: direction + name make a
  live room (default size, PLACEHOLDER description, direction-named exit pair);
  refinement is separate single-field edits. _Avoid:_ add room, create room.
- **Exemplar copy (`like=`)** — dig option copying an existing room's size +
  description; the estate-builder's stamp. Deliberately NOT a named/saved
  template system.
- **Entry room** — `Building.entry_room`: the designated way in; eviction
  fallback and the root of exit-connectivity checks. Undroppable, otherwise an
  ordinary room. _Avoid:_ entry hall (that's just its PLACEHOLDER name).
- **Building Extension** — the `BUILDING_EXTENSION` project kind: grow
  `space_budget` through the funded contribution pipe. Rooms *within* budget
  are instant and free.
- **Building Renovation** — the `BUILDING_RENOVATION` project kind (#1858):
  re-point an existing Building to a different admin-authored `BuildingKind`
  on completion, changing its descriptive flag set (e.g. a residential manor
  becomes an "Occult Manor"). Funded, owner-gated, `SINGLE_THRESHOLD`. Does
  not change `target_size` / `space_budget` (use `BUILDING_EXTENSION` /
  `BUILDING_UPGRADE`). A renovation swaps the *catalog row* (`Building.kind`),
  not per-building flags — the nine boolean flags are catalog-level cosmetic
  tags (see `BuildingKind`), so single-flag deltas are out of scope. Slice #1
  of epic #673. _Avoid:_ reclassify (ambiguous); use "renovation" for the
  catalog-kind swap specifically.
- **Building Upgrade** — the `BUILDING_UPGRADE` project kind (#1888):
  bumps an existing Building's `target_size` up to a higher tier on
  completion and re-snapshots `space_budget` from the `BuildingSizeTier`
  table (e.g. tier-3 House → tier-4 Manor grows the budget from 250 to 600).
  Funded, owner-gated, `SINGLE_THRESHOLD`. Monotonic max-set (mirrors
  `FORTIFICATION_UPGRADE`): `target_size = max(current, new_target_size)`,
  so a late-completing lower-target upgrade never regresses the size.
  Does not change `Building.kind` (use `BUILDING_RENOVATION` for that).
  _Avoid:_ size extension (that's `BUILDING_EXTENSION`, which adds flat
  budget units without changing the tier).
- **Interior Design (commission)** — the `INTERIOR_DESIGN` project kind:
  commission an admin-authored polish `ProjectTemplate` against the building or
  one room; completion applies the template's polish increments. _Avoid:_
  decoration project (RoomDecoration is the separate instant comfort-fixture
  system).
- **Map cell (placement)** — a room's building-local spot on the cosmetic map
  grid (`RoomProfile.grid_x`/`grid_y`/`floor`; north = +y). Auto-assigned on
  directional digs, moved by `place_room` (web canvas drag). Cosmetic only —
  never gates creation or play; one cell per room regardless of size; a room
  with NULL coords is *unplaced* (tray on the canvas, listed under the ASCII
  map). _Avoid:_ position (that's the within-room tactical positioning
  framework in `areas.positioning`), coordinates.
- **Throwback style** — a non-default `ArchitecturalStyle` (#1469): the
  discoverable tier (dead-civilization / far-lands). Buildable only once the
  character KNOWS a codex entry under the style's `codex_subject`, earned via
  the clue→RESEARCH pipeline; carries a `prestige_bonus` and `cost_multiplier`
  (PLACEHOLDER). _Avoid:_ classical style (ambiguous), locked style.
- **Default style** — `ArchitecturalStyle.is_default=True`: the living-realm
  tier, buildable by anyone from the start. _Avoid:_ basic style.
- **Primary home** — a persona's designated home room
  (`LocationTenancy.is_primary_home`, one active per persona; the Arx-1
  `addhome`). Anchors `prestige_from_dwellings` (home room polish + building
  polish iff the persona owns that building) and syncs the character-level
  residence (#1514 Evennia `home`). _Avoid:_ residence (that's the
  character-level Evennia `home` consumer), home room.
- **Condition tier** — `Building.condition_tier` (#1930): the qualitative
  condition ladder (Decayed → Ramshackle → Worn → Fine → Good → **Excellent**
  → Extravagantly Polished → Immaculate) whose per-tier multiplier
  step-modulates `prestige_from_dwellings`. Excellent is *normal*, held
  indefinitely by paid weekly upkeep; sustained missed upkeep slides tiers
  down (arrears accrue first — grace before slide); tiers above Excellent
  come only from a Grand Preparation and dwell-decay back. Nonpayment NEVER
  mutates polish/feature rows. The player-facing surface is the tier *label*
  (public fiction, ADR-0031); multipliers/timers stay under the hood.
  _Avoid:_ condition rating/percentage (it is a step ladder, not a creeping
  number), durability (that's `LabStationDetails`).
- **Upkeep arrears** — `Building.upkeep_arrears` (#1930): owed back-upkeep in
  coppers, accrued on missed weeks and capped at `ARREARS_CAP_WEEKS ×` weekly
  cost. Owner-only surface (never on the public renown payload); settled via
  `settle_upkeep_arrears`, and a prerequisite for refurbish/prepare. _Avoid:_
  debt (that's the org-scoped `DebtInstrument`).
- **Refurbish** — `refurbish_building` (#1930): the priced owner action
  restoring `condition_tier` to Excellent (coppers per tier deficit, scaled
  by `target_size`). Refuses on a property-granted building that hasn't been
  through `BUILDING_ACTIVATION` yet — the first-time rite lives there, not
  here. _Avoid:_ renovate/renovation (strictly the `BUILDING_RENOVATION`
  catalog-kind swap), restoration (the deleted #676 polish-refill machinery).
- **Property grant profile** — `PropertyGrantProfile`: a reusable catalog row
  configuring `grant_property_house(persona, profile)`. Generic — not tied to
  any beginning, ward, or content. A profile with `activation_target_tier`
  unset grants an already-active Building; one with it set grants an
  upkeep-exempt Building needing a `BUILDING_ACTIVATION` project to reach
  that tier. _Avoid:_ starter home, deed (this repo's `estates` app owns
  "deed"-adjacent inheritance vocabulary; a property grant is unrelated).
- **Property-granted** — a Building with `property_granted_at` set
  (`granted_via_profile` non-null): came from `grant_property_house`, not
  `complete_building_construction`. Orthogonal axis from condition tier — a
  property-granted building can be at any tier once activated.
- **Building Activation** — the `BUILDING_ACTIVATION` project kind: the
  one-time, funded arc that brings a property-granted building from its
  starting tier to `PropertyGrantProfile.activation_target_tier`, exactly
  once (`applied_at` idempotency marker, mirrors `BuildingRenovationDetails`).
  Stamps `Building.property_activated_at`, which lifts the weekly-upkeep
  exemption and un-blocks `refurbish_building`. _Avoid:_ **restoration**
  (retired #676 vocabulary — see the Refurbish entry above), **refurbish**
  (that's the separate priced-instant path for a building that already went
  through construction or activation; refurbish refuses on a granted-not-yet-
  activated building specifically so this first-time rite can't be bought
  around).
- **Grand Preparation** — the `BUILDING_PREPARATION` project kind (#1930):
  the cleaning / party-preparation loop that pushes a building one tier
  ABOVE Excellent (→ Extravagantly Polished → Immaculate) for a temporary
  prestige kick; dwell-decays back within about a week.
  `start_building_preparation` commissions it (owner-gated, arrears
  settled); the threshold is a **proportion of the house's base prestige**
  (25%/50% PLACEHOLDER, floored) — you pay for the shine on what the house
  already is. Funded via `project/donate`, sped with AP **Household
  Command** checks (`ContributionMethod` "Direct the Household");
  `complete_building_preparation` climbs the tier once, only if the
  threshold was met (underfunded lapse fizzles). _Avoid:_ polish (that's
  the per-category `BuildingPolish` value system), cleanup project
  (informal — use Grand Preparation).
- **Ultra upkeep** — `Building.ultra_upkeep` (#1930): owner-toggled premium
  (`ULTRA_UPKEEP_MULTIPLIER ×` weekly cost, on top of normal upkeep) that
  holds Immaculate past its dwell — a real recurring tradeoff, not a default.
- **Mothballed** — `Building.mothballed_at` (#1930): long owner inactivity
  (decay-tier LONG_INACTIVE, 90d+) hides the building's rooms from public
  listings (prior `is_public` snapshotted in `MothballedRoomState`) and
  freezes all upkeep/condition accrual; the owner's return restores
  everything with no back-billing. Indistinguishable from an owner privacy
  choice — carries no "inactive" label. _Avoid:_ dormant (retired #676
  concept; collides with `DecayTier.DORMANT`, the 365d player-inactivity
  tier), hidden.
