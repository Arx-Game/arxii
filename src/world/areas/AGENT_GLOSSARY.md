# Areas glossary

**Origin** (grid, #2436/#2448):
The `GridOrigin` (`world.areas.constants`) marking who authored a grid element —
AUTHORED (staff-built canonical content, the only kind that exports), STORY
(GM-built, never exported), or PLAYER (player-built, never exported). Defaults to
PLAYER so nothing exports by accident; promotion to AUTHORED is a deliberate staff
act. Carried by both `Area.origin` and `RoomProfile.origin`.
_Avoid_: authorship flag, content tier, ownership type

**Fixture key** (#2436/#2448):
The permanent, slugged identity a `RoomProfile` is assigned once at authoring time
(e.g. `arx-city/golden-hart-taproom`) — required when `origin=AUTHORED`, NULL for
runtime (`STORY`/`PLAYER`) rooms. It is the natural key `NaturalKeyMixin` resolves
on, the upsert key `grid_import.load_grid_bundles()` matches rooms by across
re-imports, and the stable reference other content fixtures (e.g. `StartingArea`)
use to point at an authored room without depending on Evennia's `ObjectDB` pk. An
`Area`'s equivalent permanent identity is its `slug`.
_Avoid_: room key, natural key (too generic — this is specifically the
grid-identity field), slug (that's the `Area`-side name for the same idea)

**Area bundle** (#2436/#2448):
The unit of grid export — one JSON document per `origin=AUTHORED` `Area`, written
to `fixtures/grid/<area-slug>.json` in the private lore repo by
`core_management.grid_export.export_grid_bundles()`. Contains that area's row, its
fixture-keyed authored rooms, the exits linking them (including cross-area exits,
identified by destination fixture key), and only the `authored:`-sourced
`LocationValueOverride`/`LocationValueModifier` sidecar rows. `core_management.
grid_import.load_grid_bundles()` reads every bundle back in four dependency-ordered
passes and never deletes an authored row absent from the bundles (reports it
instead). See ADR-0136 for the format decision and rejected alternatives.
_Avoid_: grid fixture, room fixture, area export file
