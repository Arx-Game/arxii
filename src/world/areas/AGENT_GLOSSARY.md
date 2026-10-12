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

**Elevation** (#696 gap 3):
The earned, player-declared act of raising an `Area`'s `level` one step (e.g.
NEIGHBORHOOD to WARD), gated by `AreaElevationRequirement` thresholds (held
BUILDING-level descendants + the area's ORDER stat) and a coin cost -
`world.areas.elevation_services.declare_elevation()`, dispatched via
`DeclareElevationAction` (registry key `declare_elevation`). Distinct from the
staff/GM-warrant-gated `EditAreaAction` level edit, which can still set
`area.level` directly and is not subject to these thresholds. This "one
`AreaLevel` step" sense is generic — not the feudal **Rung** below, a
specific, named unit of the Almanach's ladder.
_Avoid_: promote/promotion (already means origin promotion - PLAYER/STORY to
AUTHORED - see **Promote** above; the two concepts never overlap), level-up,
upgrade, tier-up, rung (bare, unqualified — see **Rung** below for the
specific feudal-ladder sense; "elevation" already owns the generic
one-`AreaLevel`-step meaning)

**Rung** (#3983):
One BARONY-through-EMPIRE step of the Almanach de Catenys's feudal ladder — a
`Title`'s own tier, backed by a concrete `Area` in the ordinary
`Area.parent`/`level` tree (`BARONY`(46)/`COUNTY`(53)/`DUCHY`(56)/`KINGDOM`(60)/
`EMPIRE`(65), all between `CITY` and `CONTINENT`, ADR-0309). `plant_rung`
(`world.societies.houses.almanach`) is a rung's unit of work: it mints one
`Area` per tier down to the barony at the bottom of the chain
(`TIER_TO_AREA_LEVEL` maps a `TitleTier` to its `AreaLevel`; `MARCH` shares
`COUNTY`'s level rather than getting a rung of its own), a `Domain` per chain
`Area`, and a `Title` per chain tier, all sharing one seat `Domain`. See
`docs/systems/houses.md`'s Almanach de Catenys section and
`world.societies.AGENT_GLOSSARY.md` for the ladder vocabulary built on this
(Seat, Hall, Demesne).
_Avoid_: level (bare — that's the raw `AreaLevel` enum value; a rung is
specifically a feudal-ladder step with a `Title` on it, not every `AreaLevel`
value has one); elevation (see above — that's the unrelated, generic
one-step-up act on any area, gated by `AreaElevationRequirement`, nothing to
do with titles or fealty)

**Ward** (`AreaLevel.WARD` = 30, #3983 Plan B Task 7):
A city subdivision, one step below `CITY`(40) and above `NEIGHBORHOOD`(20) —
`AreaLevel.WARD`'s own verbose label is literally "Ward". Founder- and
staff-facing copy never says "ward" for this level: the Founder Almanach's
Estate leaf and `almanach_reads._estate_payload` both call it a **district**
(`DISTRICT` in `frontend/src/almanach/copy.ts`, `HouseClaim.estate_district`).
That renaming exists BECAUSE the bare word "Ward" already means something else
entirely one glossary over — see `world.societies.AGENT_GLOSSARY.md`'s
Household entry: a house's retainer position (`ClaimKinRelation.WARD`,
ADR-0311). The two share nothing but an English word (one is a place, the
other a person's role in a household); never conflate "the city's Ward" with
"a house's Ward."
_Avoid_: ward (bare, in copy — "district" is the established copy word for
this level); sub-city, district (as the level's own technical name — it stays
`AreaLevel.WARD` in code; "district" is copy only)

**Capital** (`Area.is_capital`, #3983 Plan B Task 7):
See `world.societies.AGENT_GLOSSARY.md`'s Capital entry, the canonical
definition — a founder-mode concept (the estate gate, `plan_estate`'s anchor)
even though the field itself lives on `Area`. In short: the realm's one
designated CITY-level `Area` (`areas_one_capital_per_realm` constraint, one
per realm).
_Avoid_: see that entry's own `_Avoid_` line — "capital" is never the right
word for a title's own barony-level **Seat**.

**Pip** (#4242, ADR-0328):
One 10-mile square of the world map, the unit everything on the overland map is stored
in (`TerrainPip`, `AreaFootprintPip`, world `x`/`y`). Ten a side make a **cell**, the
100-mile square the Atlas views the map through; the cell is only a lens, never a storage
unit, so boundaries and coastlines are never cell-shaped. A barony is one pip.
_Avoid_: tile, square, hex.

**Region map** (`RegionMap`, #4242):
A region of the world map on the one world grid: an anchor cell, a width in cells, and
the generator files uploaded for it (`RegionMapUpload`, every one kept). Catenys is the
first; later regions tile beside it, their seams stitched by staff paint.
_Avoid_: world map (the grid is the world; a map is a region of it), map file (that is
the upload).

**Terrain pip** (`TerrainPip`, `Terrain`, #4242):
What one pip of ground is: water, lake, plain, forest, hill, mountain, marsh, desert,
tundra or glacier, with the generator's height and whether a river runs through it, and
its **source**: the generator's or a staff member's paint. A re-rasterize rewrites only
the generator's pips. The coast is land beside water and is read from neighbours, never
stored. Geography, distinct from `battles.TerrainType` (a battlefield's tactical shape)
and from a domain's `LandShape` (flavour prose on the record).
_Avoid_: biome (the generator's word for the input), land shape.

**Footprint** (`AreaFootprintPip`, #4242):
The set of pips a domain covers, one row per pip per area at every tier (a county's open
ground between its baronies is still the county's). A child's pip lies within its
parent's footprint; a parent cannot drop a pip a child stands on; water is never in one.
Carved and grown by `atlas_carve_footprint`, never by the generator.
_Avoid_: territory (the control stat axis, ADR-0319), bounds, extent.

**Open ground** (#4242):
A land pip no footprint holds. Real rows, claimable later; an unexplored or veiled state
is a later column on the pip, not a re-rasterize.
_Avoid_: unowned, wilderness (a terrain word), fog.

**Holder of a pip** (#4242):
The lowest-level area whose footprint contains the pip (`holder_at`), and through its
`Domain.owner_org` the house that holds it. Derived on read; never a column.
