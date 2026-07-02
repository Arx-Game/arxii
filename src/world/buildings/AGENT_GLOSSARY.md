# Buildings glossary

Domain-local vocabulary for `world.buildings` (permits, construction, the Room
Builder #670, polish/renown-from-dwellings). Root terms live in
`AGENT_GLOSSARY_MAP.md`.

- **Space budget** — the total pool of room-size units a Building can hold
  (`Building.space_budget`), snapshotted from `BuildingSizeTier[target_size]`
  at construction and grown by a Building Extension. Rooms spend from it; it is
  NOT a room count. _Avoid:_ max rooms, room cap, room budget.
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
- **Interior Design (commission)** — the `INTERIOR_DESIGN` project kind:
  commission an admin-authored polish `ProjectTemplate` against the building or
  one room; completion applies the template's polish increments. _Avoid:_
  decoration project (RoomDecoration is the separate instant comfort-fixture
  system).
- **Primary home** — a persona's designated home room
  (`LocationTenancy.is_primary_home`, one active per persona; the Arx-1
  `addhome`). Anchors `prestige_from_dwellings` (home room polish + building
  polish iff the persona owns that building) and syncs the character-level
  residence (#1514 Evennia `home`). _Avoid:_ residence (that's the
  character-level Evennia `home` consumer), home room.
