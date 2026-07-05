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
