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
_Avoid_: canonize, publish, author (verb form — "author" stays the noun/adjective
for who built something, see **Origin** above)

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
