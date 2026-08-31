# Areas glossary

**Origin** (grid, #2436/#2448):
The `GridOrigin` (`world.areas.constants`) marking who authored a grid element —
AUTHORED (staff-built canonical content, the only kind that exports), STORY
(GM-built, never exported), or PLAYER (player-built, never exported). Defaults to
PLAYER so nothing exports by accident; promotion to AUTHORED is a deliberate staff
act. Carried by both `Area.origin` and `RoomProfile.origin`.
_Avoid_: authorship flag, content tier, ownership type

**Fixture key** (#2436/#2448, extended #2451):
The permanent, slugged identity a `RoomProfile` is assigned once at authoring time
(e.g. `arx-city/golden-hart-taproom`) — required when `origin=AUTHORED`, NULL for
runtime (`STORY`/`PLAYER`) rooms. It is the natural key `NaturalKeyMixin` resolves
on, the upsert key `grid_import.load_grid_bundles()` matches rooms by across
re-imports, and the stable reference other content fixtures (e.g. `StartingArea`)
use to point at an authored room without depending on Evennia's `ObjectDB` pk. An
`Area`'s equivalent permanent identity is its `slug`. The same nullable-unique
`fixture_key` field (same contract: set when authored from the staff canvas, NULL
for ad hoc/test rows) was added to `world.clues.RoomClue`/`ClueTrigger` and
`world.magic.PortalAnchor` (#2451, epic #2436 slice 4) so discovery/portal
placements can be exported/reimported the same way rooms are — it is the
`clues`/`clue_triggers`/`portal_anchors` grid-bundle sidecar section's upsert key.
_Avoid_: room key, natural key (too generic — this is specifically the
grid-identity field), slug (that's the `Area`-side name for the same idea, and —
separately — `Clue`'s own natural key for content-pipeline export, #2451)

**Promote** (#2436/#2449):
The one-way act of assigning an `Area` or `RoomProfile`'s permanent identity key
(`slug`/`fixture_key`) and flipping its `origin` to AUTHORED —
`world.areas.grid_services.promote_to_authored()`, reached from the staff canvas
via the `promote_room`/`promote_area` actions. Assignment-time and permanent
(ADR-0140): re-promoting with a *different* key raises; re-promoting with the
*same* key is a no-op success. `staff_dig_room` promotes its room implicitly
(every room it creates is born AUTHORED with a suggested key) — `promote_room`
exists for a room dug some other way (or a `STORY`/`PLAYER` room being adopted
into the canon), not as the only path to AUTHORED status.
_Avoid_: canonize, author (verb form — "author" stays the noun/adjective
for who built something, see **Origin** above), publish (that is the separate
live-world visibility act — see **Publish** below; a room can be promoted yet
unpublished, or published yet never promoted)

**Area bundle** (#2436/#2448):
The unit of grid export — one JSON document per `origin=AUTHORED` `Area`, written
to `fixtures/grid/<area-slug>.json` in the private lore repo by
`core_management.grid_export.export_grid_bundles()`. Contains that area's row, its
fixture-keyed authored rooms, the exits linking them (including cross-area exits,
identified by destination fixture key), and only the `authored:`-sourced
`LocationValueOverride`/`LocationValueModifier` sidecar rows. `core_management.
grid_import.load_grid_bundles()` reads every bundle back in four dependency-ordered
passes and never deletes an authored row absent from the bundles (reports it
instead). See ADR-0140 for the format decision and rejected alternatives.
_Avoid_: grid fixture, room fixture, area export file

**Publish** (#3477):
The act of making a room exist in the live world — `staff_publish_room` stamping
`RoomProfile.published_at`. Rooms are born unpublished: not enterable, exits into
them hidden, invisible to players until a human publishes (WIP until then, honor
system, no doneness machinery). Publish rights ride build rights — no second
approval tier. Orthogonal to **Promote** (canon identity/export) and to `origin`:
publishing answers "can players walk in," promotion answers "does this export."
_Avoid_: activate, go-live, release; promote (see above)

**Warrant** (#3477):
The one authorization concept for build actions, staff and GM alike (players
later, via permits riding the same interface): *is this spot inside your
territory, is this level within your ceiling, is there budget left.* Backed by
`world.gm.AreaBuildGrant` (account, `Area` subtree via `AreaClosure`, `AreaLevel`
ceiling, optional room budget); staff carry an implicit all-world warrant.
Enforced in action prerequisites (`BuildWarrantPrerequisite`), never the UI — the
Atlas merely reflects it (view rooted at the grant, add-affordances past the
ceiling absent).
_Avoid_: build permission, grant (bare — the model row is a grant, the concept the
actor holds is the warrant), ACL

**Build** (#3477):
A player-designed construct of any size or dimension — what a permit produces. May
be open-air (four field-quadrant rooms are a build); deliberately NOT "building".
_Avoid_: building (see below — the words never substitute), construction, lot

**Building** (#3477):
The `AreaLevel.BUILDING` hierarchy level and its mechanics (holds only rooms, no
child areas; the Lattice's `'rooms'` mode). A build may *contain* a building; the
words never substitute for each other.
_Avoid_: build (see above), structure (as a synonym)
