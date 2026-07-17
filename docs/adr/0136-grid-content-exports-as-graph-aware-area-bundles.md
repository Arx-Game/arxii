# Grid content exports as graph-aware, per-area bundles keyed by permanent slugs

The game-world grid (`Area` hierarchy, `RoomProfile`-wrapped `ObjectDB` rooms, exits,
and their `LocationValueOverride`/`LocationValueModifier` sidecars) is an object graph,
not a set of independent rows — `content_export.py`'s flat natural-key serializer can't
express "these rooms belong to this area, these exits connect those rooms." `grid_export.py`
(#2436/#2448) instead writes one JSON bundle per `origin=AUTHORED` (`world.areas.constants.GridOrigin`)
`Area` to `fixtures/grid/<area-slug>.json` in the lore repo: the area row, its authored
rooms keyed by a permanent `RoomProfile.fixture_key`, its exits (upsert key `(source
fixture_key, exit db_key)`), and only the sidecar rows that are genuinely authored — every
`LocationValueOverride` plus `LocationValueModifier` rows whose `source` carries the
reserved `authored:` prefix, so weather/sanctum-growth/building-style writers never get
swept into a bundle. `GridOrigin` (AUTHORED/STORY/PLAYER) is the export gate: only staff
promoting content to AUTHORED (a deliberate act, never a default) makes it exportable, so
GM-improvised `STORY` areas and player-built `PLAYER` rooms can never leak into the lore
repo. `grid_import.py`'s `load_grid_bundles()` reads every bundle back in four passes
(areas topologically by parent slug, rooms by `fixture_key`, exits by source/destination
key, sidecars scoped to each bundle's area/rooms) and is report-never-delete: an AUTHORED
area/room/exit present in the DB but absent from every bundle surfaces as a report line,
never a deletion, and only `authored:`-sourced modifiers are ever replaced wholesale.
Rejected: stretching per-model natural-key fixtures (the existing `content_export.py`/
`load_entries` pipeline) over `ObjectDB` rooms — Evennia's rows are pk-based with no
natural key, and alphabetical per-model load order can't sequence a graph where an exit
needs its destination room to exist first. Also rejected: Evennia's own `dump`/`load` —
pk-based identity that doesn't survive a fresh database, and no way to carry the Django
sidecar models (`LocationValueOverride`, `ObjectDisplayData`) alongside the room. Grid
identity (`Area.slug`, `RoomProfile.fixture_key`) is therefore assignment-time and
permanent, chosen once at authoring and never regenerated — the opposite of `ObjectDB`'s
pk, which is an implementation detail. A consequence worth naming: runtime-only tables
(`LocationOwnership`, `LocationTenancy`, `RoomDecoration`, `RoomFeatureInstance`, and every
non-`authored:` modifier) never export at all — the grid bundle is a canonical-content
snapshot, not a live-game backup, and player/GM state is expected to be rebuilt or
re-earned after a fresh-database import, never restored from a bundle.

> Status: accepted · Source: epic #2436, slice 1 issue #2448 · Related: ADR-0120
> (cross-Area travel rides the exit graph — same "coordinates are cosmetic, exits are the
> only real graph" principle applied here to export), ADR-0121 (portal anchors as a
> stackable magic model — the sidecar shape slice 4's bundle section will extend)
