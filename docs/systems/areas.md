# Areas System

Spatial hierarchy for organizing rooms into buildings, neighborhoods, wards, baronies,
counties, duchies, kingdoms, empires, continents, worlds, and planes. The ladder is sizes only
(#4085): a barony is the actual holding a title or a Lord Mayor stands on, whatever its shape
(a city, a fortress, a temple), and there is no "region" rung; the boundary word travels across
is not a size (see `docs/systems/secrets.md`, gossip reach).

**Source:** `src/world/areas/`

---

## Enums (constants.py)

```python
from world.areas.constants import AreaLevel
# BUILDING(10), NEIGHBORHOOD(20), WARD(30), BARONY(40), COUNTY(53), DUCHY(56),
# KINGDOM(60), EMPIRE(65), CONTINENT(70), WORLD(80), PLANE(90)
# (CITY was 40 and BARONY 46 until #4085 merged them at 40; REGION (50) was retired.)
```

### Feudal rungs (#3983)

`COUNTY`/`DUCHY`/`EMPIRE` were added between `BARONY` and `CONTINENT` so a duchy can
contain a county, a county a barony, on the same `Area.parent` map/tree the rest of the Atlas
ladder already walks — no parallel hierarchy (`BARONY` absorbed the old `CITY` at value 40 in
#4085, so a city is a barony, ADR-0310). `KINGDOM` (pre-existing) sits between `COUNTY` and
`EMPIRE`. The Almanach de Catenys's `TitleTier` (`world.societies.houses.constants`:
empire/kingdom/duchy/march/county/barony, #3091's six-step noun ladder) maps onto these levels via
`TIER_TO_AREA_LEVEL` — `MARCH` is a county-tier holding and shares `AreaLevel.COUNTY` rather than
getting a rung of its own:

```python
TIER_TO_AREA_LEVEL: dict[str, int] = {
    TitleTier.EMPIRE: AreaLevel.EMPIRE,
    TitleTier.KINGDOM: AreaLevel.KINGDOM,
    TitleTier.DUCHY: AreaLevel.DUCHY,
    TitleTier.MARCH: AreaLevel.COUNTY,
    TitleTier.COUNTY: AreaLevel.COUNTY,
    TitleTier.BARONY: AreaLevel.BARONY,
}
```

`world.societies.houses.almanach.plant_rung` is what actually mints a rung: it plants one `Area`
per tier down to the barony seat (`_CHAIN_BELOW`), a `Domain` per chain `Area` (1:1 with `Area`),
and a `Title` per chain tier, all sharing one seat `Domain` — so every title, however high, always
has a concrete barony-level seat underneath it and the liege walk never runs out of ancestors to
climb. See `docs/systems/houses.md`'s Almanach de Catenys section for the full ladder rules
(liege-by-containment, re-homing, demesne/vassal counts) and ADR-0309.

### Capital (`Area.is_capital`, #3983 Plan B)

A realm's one designated CITY-level `Area` (`areas_one_capital_per_realm`, a
`UniqueConstraint(fields=["realm"], condition=Q(is_capital=True))` — a realm may have
zero, never more than one). Read by `almanach_reads.charter_for_realm`'s `capital_name`
and gated on by the founder claim's estate pitch (`creator._validate_kin_and_lands`
refuses `estate_name` with "That realm has no capital yet" when absent);
`almanach.plan_estate` plants a founder's or staff member's estate `Area` under it (or
under a named district within it — a WARD-level `Area`, `HouseClaim.estate_district`).
Distinct from a title's own **Seat** (`docs/systems/houses.md` — a landed title's own
barony-level demesne; see `world.societies.AGENT_GLOSSARY.md`'s Capital entry, the
canonical definition, for the full distinction).

---

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Area` (SharedMemoryModel) | A spatial hierarchy node at a specific level | `name`, `level` (AreaLevel), `parent` (self-FK), `realm` (FK to `realms.Realm`), `description`, `grid_x`/`grid_y` (nullable, parent-local rendering coordinates, #2223), `is_capital` (bool, one per realm, #3983 Plan B — see "Capital" below) |
| `AreaClosure` | Read-only materialized view for transitive closure | `ancestor` (FK), `descendant` (FK), `depth` |
| `AreaElevationRequirement` | Authored config: what a declarer must hold/pay to elevate an area to `to_level` (#696 gap 3) | `to_level` (unique AreaLevel), `min_held_buildings`, `min_order_stat`, `cost_coppers` (all PLACEHOLDER) |

---

## Key Methods

### Area Model

```python
from world.areas.models import Area

# Validation on save: child level must be < parent level, no circular chains
area = Area(name="Market District", level=AreaLevel.NEIGHBORHOOD, parent=city_area)
area.save()  # Runs full_clean() and refreshes AreaClosure materialized view

area.delete()  # Also refreshes AreaClosure
```

### Service Functions

```python
from world.areas.services import (
    get_ancestry,            # Full ancestor chain from root down to area
    get_ancestor_at_level,   # Find ancestor at specific AreaLevel
    get_effective_realm,     # Walk up hierarchy to find nearest realm
    get_descendant_areas,    # All areas in the subtree below
    get_rooms_in_area,       # All RoomProfiles in area and descendants
    reparent_area,           # Move area under a new parent (auto-refreshes closure)
    get_room_profile,        # Get or create RoomProfile for a room ObjectDB
    area_grid_path,          # Root->area chain of parent-local (grid_x, grid_y) pairs
)
```

### Coordinates (`grid_x`/`grid_y`, #2223)

`Area.grid_x`/`grid_y` are nullable integers giving an area's position within its
**own parent's** local grid — rendering/hint data only, mirroring `RoomProfile.grid_x`/
`grid_y`'s convention one level up the hierarchy. They are never consulted for routing
(see `find_route()` below and ADR-0120): connectivity is exits, full stop.

```python
from world.areas.services import area_grid_path

# Root -> area chain of parent-local (grid_x, grid_y) pairs, one entry per
# ancestor (via get_ancestry); unset coordinates come back as (None, None).
path = area_grid_path(market_area)
# Composing this into a single global position is a future renderer's job,
# not this helper's — each entry is only meaningful among its own siblings.
```

### Ancestry Queries (via AreaClosure materialized view)

```python
from world.areas.services import (
    containing_areas,
    get_ancestry,
    get_ancestor_at_level,
    get_effective_realm,
)
from world.areas.constants import AreaLevel

# Get full ancestry (single indexed query via materialized view)
ancestry = get_ancestry(market_area)
# Returns: [Plane, World, Continent, Kingdom, County, Barony, Ward, Market District]

# Find the barony (the city) this area belongs to
city = get_ancestor_at_level(market_area, AreaLevel.BARONY)

# The same chain by walking parent links, self first (no matview; safe on the SQLite tier)
chain = containing_areas(market_area)

# Walk up to find the nearest realm assignment
realm = get_effective_realm(market_area)
```

### Room Queries

```python
from world.areas.services import get_rooms_in_area

# Get all rooms in an area and everything beneath it
rooms = get_rooms_in_area(city_area)
# Returns list of RoomProfile instances with objectdb and area select_related
```

---

### One-way exits and unfiled rooms (#3860, ADR-0301)

Every exit-minting surface makes a symmetric pair through `grid_services.create_exit_pair`,
except the two staff tools that may leave the return out on purpose:
`StaffLinkRoomsAction` with `one_way=True` (through the public `grid_services.create_exit`,
one direction, no `name_ba` needed; the message reads `Linked A -> B (one way).`) and the
Atlas's exit dialog (`atlas/AddDialog.tsx` exit mode, and the canvas's `LinkRoomsDialog`),
where "Both ways" is pressed by default and "One way" hides the return name and says
nothing leads back. The owner's building `link_rooms` and a GM's `story_link_rooms` stay
two-way. Exit rows in the area manager (`WorldBuilderExitSerializer`) and the room detail
(`WorldBuilderExitDetailSerializer`) carry `one_way`, from `grid_services.one_way_exit_ids`
(one query per payload); the room document's exit chip tags it, and
`StaffUnlinkRoomsAction` already removes an exit with no sibling.

Rooms with no `Area` (Limbo, and anything minted outside the builder) sit on no grid.
`GET /api/world-builder/areas/unfiled-rooms/` lists them (`WorldBuilderRoomHitSerializer`
rows; staff only in effect, since a warrant covers areas and an area-less room lies under
none, so a grant holder gets `[]`), and the Atlas's index rail shows them under "Unfiled
rooms" (`atlas/IndexRail.tsx`), each opening the room's document. The room search already
found them by name; the rail is how a staffer reaches one without knowing to search.

## World map (`worldmap/`, #4242, ADR-0328)

The continent at pip resolution. A **pip** is a 10-mile square; ten a side make the
100-mile **cell** the Atlas views the map through. Everything stored is pips; the cell is
only a lens. A **barony is one pip**; a county is roughly a hundred and may spill over a
cell edge; boundaries and coastlines are never cell-shaped.

| Model | Role | Key fields |
|---|---|---|
| `RegionMap` | A region on the one world grid | `name`, `area` (nullable FK to the CONTINENT-level Area it is the geography of), `anchor_x`/`anchor_y` (world cells), `width_cells`, `height_cells` (from the first upload's aspect), `created_by`/`created_at`; `pip_x0`/`pip_y0` properties give the first pip |
| `RegionMapUpload` | One uploaded generator file, kept whole | `region`, `file_name`, `file_bytes` (gzip `BinaryField`), `byte_size`, `generator_version`, `source_width_px`/`source_height_px`, `uploaded_by`/`uploaded_at`, `rasterized_at`. Append-only: every file is kept |
| `TerrainPip` | One pip of ground | `region` (PROTECT), `x`/`y` (world pips, unique together), `terrain` (`Terrain`), `height` (the generator's 0-100), `has_river`, `source` (`PipSource`: generator or staff) |
| `AreaFootprintPip` | One pip of ground and the lowest area holding it | `area` (CASCADE), `x`/`y` (unique together: one holder per pip); every ancestor's footprint is derived by walking `Area.parent` from the holders, so containment holds by construction |

**Enums** (`worldmap/constants.py`): `Terrain` (water, lake, plain, forest, hill,
mountain, marsh, desert, tundra, glacier; the coast is derived from neighbours, never
stored) and `PipSource` (generator, staff). `PIPS_PER_CELL = 10`, `MILES_PER_PIP = 10`.
`Terrain` is geography; `battles.TerrainType` is a battlefield's tactical shape and the
two share nothing. `LandShape` on a domain is flavour prose, not this.

**The rasterizer** (`worldmap/azgaar.py`): `parse_map(text)` reads a Fantasy Map
Generator `.map` file by content (the params line, then the grid block beginning
`{"spacing":` and the five grid arrays after it, then the feature list; rivers from the
SVG's river layer); `rasterize(gmap, width_cells, height_cells)` returns one `RasterPip`
per pip, scaling the file to the region's width and finding each pip's grid cell the
generator's own way. Terrain: sea below height 20 (lake when the feature is a lake),
mountain from 71, hill from 50, otherwise the generator's biome matrix over temperature
and moisture (its own rule: four plus the mean precipitation of the cell and its land
neighbours, plus two on a river). Only the grid arrays are read; the generator's states,
provinces and burgs are ignored by ruling.

**Services** (`worldmap/services.py`), each refusing with `WorldMapServiceError.user_message`:

```python
create_region_map(*, name, anchor_x, anchor_y, width_cells, area=None, new_continent=False, actor=None)  # refuses overlap; new_continent links the CONTINENT rung by the region's name, creating an authored one when there is none
import_region_map_file(*, region, file_name, data, actor=None)  # parse, keep, rasterize
rasterize_upload(upload)  # re-run the rasterize step from a kept file
paint_terrain(*, region, pips, terrain)  # staff pips, survive every upload
set_footprint(*, area, add=(), remove=()) -> FootprintChange  # takes what it may and skips the rest: carving inside an ancestor moves its row down, shrinking hands it back up; another domain's pip and a descendant's pip are skipped and counted by holder name; water is taken like land
footprint_of(area)  # every pip inside an area: its own rows and its descendants'
holder_at(x, y)  # the area whose row holds the pip, or None (open ground)
region_read(region)  # the pips payload: terrain rows + footprints with holder, title, seat
```

A re-rasterize deletes the region's generator pips and writes the new raster, skipping
any square a staff pip holds (ruling 5 on #4242). A footprint below BARONY is refused. A pip has one row naming its lowest holder: a barony
carved inside a county takes the county's row, and the county's footprint still contains the pip
because ancestors are derived from the holders; a barony claiming open ground grows every
ancestor with it. A carve is a drag, and a drag takes what it may (#4317): a pip another domain
holds, or one a descendant stands on when shrinking, is skipped rather than refusing the whole
sweep, and the `FootprintChange` names the holders skipped so the action's message can say so.
Water is a pip like any other: a realm's footprint includes its territorial waters (ApostateCD,
2026-10-12, reversing the spec's land-only rule on #4242).

**Actions** (`actions/definitions/atlas_map.py`, `category="almanach"`, staff only):
`atlas_create_region_map`, `atlas_carve_footprint` (`area_id`, `add`/`remove` as `[x, y]`
lists), `atlas_paint_terrain` (`region_id`, `pips`, `terrain`). Create Domain from the
map is `almanach_plant_rung` then `atlas_carve_footprint`; nothing here mints a rung.

**API** (`worldmap/views.py`, on the world-builder router, `IsAdminUser`):
`GET /api/world-builder/region-maps/`, `GET .../<id>/`, `GET .../<id>/pips/` (the
`region_read` payload: `pips` rows are `[x, y, terrain, river]`, `footprints` carry
`holder_org_id`, `title_id` for the Almanach link, `seat`), `POST .../<id>/upload/`
(multipart `file`; the one write that is not an action), `GET .../<id>/file/` (the latest
upload, decompressed, under its original name).

**Frontend:** the Atlas's region-map view (`frontend/src/world-builder/atlas/RegionMapPage.tsx`,
view kind `regionmap`, reached from the index rail's Maps section): pips on one canvas
in flat colour, cell lines every ten pips, footprints as holder-coloured fills, the seat
as a dot; modes select, carve and paint; writes dispatch through `runAction`. The rail's
New region form carries a continent choice: a new CONTINENT rung by the region's name
(the default, `new_continent`), an existing continent (`area_id`), or none; an area page's
On the map prefers the region linked to that area.

## AreaClosure Materialized View

The `AreaClosure` model is backed by a Postgres materialized view that stores every ancestor-descendant pair with depth. This enables efficient ancestry and descendant queries without recursive CTEs at query time.

- **Refreshed automatically** when any `Area` is saved or deleted via `refresh_area_closure()`
- **Not Django-managed** (`managed = False`), created via migration with raw SQL
- Enables single-query ancestry lookups instead of walking parent chains

```python
from world.areas.models import AreaClosure, refresh_area_closure

# Direct query: find all ancestors of an area
AreaClosure.objects.filter(descendant=area).order_by("-depth")

# Direct query: find all descendants
AreaClosure.objects.filter(ancestor=area, depth__gt=0)

# Manual refresh (normally automatic)
refresh_area_closure()
```

---

## Admin

- `AreaAdmin` - List with name, level, parent, realm; filterable by level and realm; autocomplete for parent and realm
- `AreaElevationRequirementAdmin` - List with to_level, min_held_buildings, min_order_stat, cost_coppers; filterable by to_level

---

## Elevation (`elevation_services.py`, #696 gap 3)

The **earned, player-declared** path to raise an `Area`'s `level` one rung, distinct
from the staff/GM-warrant-gated `EditAreaAction` level edit
(`actions/definitions/world_builder.py`), which can still set `area.level` directly
regardless of these thresholds. "Elevation" is the canonical term for this earned
path; "promotion" already means origin promotion (`GridOrigin` PLAYER/STORY ->
AUTHORED) elsewhere in this app, so the two never overlap.

```python
from world.areas.elevation_services import (
    declare_elevation,
    elevation_eligibility,
    held_building_count,
    next_level,
)

next_level(area)  # -> the AreaLevel value one rung above area.level, or None at PLANE

result = elevation_eligibility(area, declarer=persona)
# ElevationEligibility(eligible, held_buildings, order_stat, requirement, reasons)

area = declare_elevation(area, declarer=persona, treasury_or_purse=purse_or_treasury)
# Re-checks eligibility inside a transaction, sinks cost_coppers via
# currency.services.transfer (no destination - a pure coin sink), writes
# area.level, raises ValidationError (carrying `reasons`) when ineligible.
```

`elevation_eligibility` checks two thresholds from the `AreaElevationRequirement` row
keyed on `next_level(area)`:

- **Held buildings** - how many of the area's BUILDING-level descendants the declarer
  effectively holds. "Effectively holds" reuses Task 1's
  `locations.services.effective_owner_for_area`: the declarer's own persona, or an
  organization they lead (`houses.services.is_org_leader`) - not
  `can_administer_domain`, which also accepts the `domain-steward` office but requires
  a `Domain` instance, and a BUILDING-level area's owner need not be a `Domain` at all.
  BUILDING is `AreaLevel`'s floor (no level exists below it), so a BUILDING-level area
  is always a leaf and can never itself have BUILDING descendants - the held-buildings
  threshold only bites at NEIGHBORHOOD+ areas elevating into WARD+.
- **Area order** - `locations.services.area_stat_total(area, StatKey.ORDER)`, summed
  across the area's own + ancestor `LocationValueModifier` rows.
  `locations.services.area_order_difficulty(area)` turns order versus crime into a
  check difficulty (NORMAL shifted by CRIME minus ORDER, clamped to the authored
  bands): the collection run and a task's issue-time check both read it (#696).

`DeclareElevationAction` (`actions/definitions/areas.py`, REGISTRY key
`declare_elevation`) is the in-play entry point: it gates on the declarer's active
persona being the AREA's own effective owner (not just its buildings'), resolves an
optional `organization_id` kwarg to spend from that org's treasury instead of the
declarer's own purse (mirrors `events._resolve_grandeur_source`, gated on
`can_spend_treasury`), then defers to `declare_elevation`'s own re-check.

Only one `AreaElevationRequirement` row is seeded (`world.areas.seeds.
ensure_area_elevation_content`): `to_level=NEIGHBORHOOD` with `min_held_buildings=0`
(BUILDING areas can never hold BUILDING descendants, so this threshold is a no-op at
the first rung) and PLACEHOLDER `min_order_stat`/`cost_coppers`. Higher tiers (WARD+,
where held buildings become meaningful) are unseeded pending a staff authoring pass.

---

## Presence & Travel (`where` / `travel`, #1463 + #2163)

Room-to-room navigation layered on the Area hierarchy: a public presence directory
(`where`) listing every character currently in a publicly-listed room, and a
pathfinder + auto-walk pair (`travel`) that lets a player "go there" to any of them.

### `where_listing` (`src/world/areas/services.py`, #1463)

```python
from world.areas.services import WhereEntry, where_listing

# One entry per online, non-concealed, non-hidden character in a publicly-listed
# room, sorted by persona name.
entries = where_listing(viewer_account=account)
# WhereEntry(persona_name: str, room_path: str, room_id: int)
```

`room_path` is the coloured `Area` ancestry path (`colored_area_path()`, see
above). `room_id` (#2163 addition) is the destination room's pk — added so a
`where` row can dispatch a `travel_to` Action directly without re-resolving the
room by name.

### `find_route()` (`src/world/areas/positioning/travel.py`, #2163)

```python
from world.areas.positioning.travel import find_route

route = find_route(origin_room, destination_room)
# -> list[ObjectDB] (an ordered list of Exit objects) | None
```

Frontier-batched BFS: each level fetches every outbound exit for the *entire*
current frontier in one query (mirroring `area_subtree_pks`'s
`parent_id__in=[...]` batching over the Area tree above), rather than one room
at a time — the fix for the per-room-query blowup that breaks naive BFS at
scale. Crosses Area boundaries freely (#2223, ADR-0120): the exit graph IS the
connectivity — any room-level `Exit` is a valid hop whatever Area it lands in,
with no separate Area-to-Area adjacency model to consult. Still scoped to
publicly-listed rooms only (`room_is_publicly_listed`), matching the `where`
privacy invariant (#1287): a route never passes through, or reveals, a private
room. Capped at `settings.TRAVEL_MAX_HOPS` (default 50), hop-counted across
Area boundaries the same as within one. Returns `None` when unreachable, the
destination isn't public, or the route would exceed the hop cap; returns `[]`
when already at the destination.

### `TravelAction` / `StopTravelAction` (`src/actions/definitions/movement.py`, #2163)

REGISTRY actions (keys `"travel_to"` / `"stop_travel"`) — a server-paced,
cancellable auto-walk. `TravelAction` computes a route via `find_route()` and
schedules one hop per `hop_delay_seconds` (1.5s) via `evennia.utils.delay()`,
reusing the same `check_exit_traversal`/`traverse_exit` primitives a manual
`TraverseExitAction` hop uses, so room-state broadcasts happen exactly as they
do for a manual walk. A per-caller `.ndb.active_travel_token` makes
cancellation/re-dispatch safe: every scheduled hop callback checks its token
against the caller's *current* active token before acting, so a stale callback
from a superseded or stopped walk silently no-ops instead of moving the player
unexpectedly. `StopTravelAction` cancels the pending `.ndb.active_travel_task`
and clears the token.

### Telnet (`src/commands/travel.py`, #2163)

`CmdTravel` (`travel <character name>` / `travel stop`) resolves the named
character's current room and dispatches `TravelAction`/`StopTravelAction`.

### Frontend (#2163)

"Go there" buttons on the scene browser (`ScenesListPage`,
`frontend/src/scenes/pages/`) and the presence panel (`PresencePanel`,
`frontend/src/game/components/`) dispatch the `travel_to` REGISTRY action with
the row's room id (the scene's room, or `WhereEntry.room_id`).

---

## Positioning Submodule (`src/world/areas/positioning/`)

Room-anchored spatial graph: named position nodes, traversable edges, per-object occupancy, capability-gated movement, and GM terrain blueprints for non-combat scene staging.

### Enums

```python
from world.areas.positioning.constants import PositionKind
# PRIMARY, FEATURE (authored regions: balcony, altar, pit),
# ELEVATED (catwalk, balcony rim),
# AERIAL (auto-created by flight services; exists only while airborne objects occupy the room),
# BARRIER_SIDE (reserved; dynamic carving),
# CHASM (below-ground level; entering one emits EventName.FELL)

AERIAL_PROPERTY_NAME = "aerial"  # ObjectProperty tag set on airborne objects
```

### Models [BUILT & WIRED]

**Abstract bases** (`models.py`):

| Base | Purpose |
|------|---------|
| `PositionNodeBase` | `name`, `kind` (`PositionKind`), `description`, and the cover facts `is_roofed` / `screens_ranged` (#4608, ADR-4608-A) — shared by `Position` and `BlueprintPosition`; `instantiate_blueprint` copies all of them, and the blueprint admin lists and filters both flags |
| `PositionEdgeBase` | `is_passable`; `_validate_canonical()` helper (self-loop + pk-ascending canonical-order) — shared by `PositionEdge` and `BlueprintEdge` |

**Live room graph** (room-anchored):

| Model | Purpose | Key Fields / Constraints |
|-------|---------|--------------------------|
| `Position` | Named tactical region in a room | `room` FK → `objects.ObjectDB`; unique per room+name; `elevation_anchor` (self-referential FK → `Position`, null=floor/top-level) — the ground `Position` this AERIAL or CHASM node is anchored to (**omitted from `MODEL_MAP.md`** — the auto-generation tool skips self-referential FKs); `layout_x`/`layout_y` (nullable small integers) — cosmetic tactical-map coordinates (#2006); `null` on both means "let the frontend auto-layout" (`computeTacticalLayout`'s BFS-ring placement) rather than "place at the origin" |
| `PositionEdge` | Traversable adjacency between two `Position` nodes | `position_a` / `position_b` FK (canonical pk order); `is_passable`; `blocks_flight` — obstructs AERIAL-layer traversal; `gating_challenge` FK → `mechanics.ChallengeInstance` (nullable, `SET_NULL`); `duration_rounds` / `created_by_sheet` (a conjured wall's lifetime and caster); `integrity` / `max_integrity` (nullable `PositiveSmallIntegerField`, #4606 — a conjured wall's strength; both null = indestructible; `CheckConstraint` both-or-neither and `integrity <= max_integrity`); `source_rampart` FK → `Rampart` (nullable, `SET_NULL`, `related_name="sealed_edges"`, #4606 — the Rampart whose seal this is; a `CheckConstraint` forbids it together with `integrity`, since the Rampart holds that pool); `barrier_integrity` property → `(integrity, max_integrity)` from the Rampart or the edge, else `None` |
| `ObjectPosition` | One-to-one occupancy record | `objectdb` OneToOne PK; `position` FK — mirrors `db_location` |

**Rampart — living barriers** (#2209, room-anchored; see the dedicated section below):

| Model | Purpose | Key Fields / Constraints |
|-------|---------|--------------------------|
| `Rampart` | A projected barrier covering one `Position` | `position` `OneToOneField` → `Position` (`related_name="rampart"`, one rampart per position); `element_profile` FK → `RampartElementProfile` (`PROTECT`); `integrity` / `max_integrity` (`PositiveSmallIntegerField`); `created_by_sheet` FK → `CharacterSheet` (`SET_NULL`, null=staff-authored); `duration_rounds` (null=until collapse or scene end); `crack_state` property (INTACT/CRACKED/CRUMBLING band read off `integrity`/`max_integrity`) |
| `RampartElementProfile` | An authored, reusable element (Stone/Wind/Fire/Thorn) | `name` (unique); `signature_behavior` (`RampartSignature`: SEAL_EDGES, MISSILE_WARD, MELEE_RETALIATION, GRASPING); `signature_value`; `signature_damage_type` / `signature_condition` FK (nullable, behavior-specific) |
| `RampartElementResistance` | Per-damage-type resist/vulnerability row for a profile | `profile` FK → `RampartElementProfile` (`CASCADE`); `damage_type` FK (`PROTECT`); `value` (signed — positive resists, negative is a vulnerability); unique per (profile, damage_type) |

**Blueprint template graph** (room-independent):

| Model | Purpose | Key Fields / Constraints |
|-------|---------|--------------------------|
| `PositionBlueprint` | GM-authored reusable terrain layout | `name` (unique), `description` |
| `BlueprintPosition` | Position node template inside a blueprint | `blueprint` FK; name unique per blueprint; `layout_x`/`layout_y` (nullable small integers, #2006) |
| `BlueprintEdge` | Edge template inside a blueprint | `blueprint` FK; `position_a` / `position_b` FK → `BlueprintPosition` (canonical pk order); `is_passable`; `gating_challenge_template` FK → `mechanics.ChallengeTemplate` (nullable, `on_delete=PROTECT`) |

**Room profile link** (in `evennia_extensions.RoomProfile`):

- `default_blueprint` — nullable FK → `areas.PositionBlueprint`; used by the "Set the Stage" quick action.

### Services [BUILT & WIRED]

**`src/world/areas/positioning/services.py`**

*Live room graph authoring:*

| Function | Summary |
|----------|---------|
| `create_position(room, name, *, kind, description)` | Create a `Position` in a room |
| `remove_position(position)` | Delete (cascades edges + occupancy) |
| `connect_positions(a, b, *, is_passable, gating_challenge)` | Create a canonical `PositionEdge` (auto-reorders pk) |
| `disconnect_positions(a, b)` | Remove the edge between two positions |

*Blueprint authoring:*

| Function | Summary |
|----------|---------|
| `create_blueprint(name, *, description)` | Create a `PositionBlueprint` |
| `add_blueprint_position(blueprint, name, *, kind, description)` | Create a `BlueprintPosition` |
| `connect_blueprint_positions(a, b, *, is_passable, gating_challenge_template)` | Create a `BlueprintEdge` (raises `PositionError` for cross-blueprint) |
| `remove_blueprint(blueprint)` | Delete blueprint and its positions/edges (cascade) |

*Staging:*

| Function | Summary |
|----------|---------|
| `instantiate_blueprint(blueprint, room, *, replace=False)` | Clone a blueprint's position graph into a room (returns new `Position` list). For each gated `BlueprintEdge` (`gating_challenge_template` set), mints a live `ChallengeInstance` via `instantiate_challenge` (`world.mechanics.challenge_resolution`) and sets it on the cloned `PositionEdge.gating_challenge`. Raises `PositionError` if already staged and `replace=False`; raises `PositionError` if occupied when `replace=True`. Runs atomically. |

*Query:*

| Function | Summary |
|----------|---------|
| `position_reachable(origin, target, reach)` | Reach-semantics check (SAME / ADJACENT / REACH_N / ANY). The cover rules come first (#4608): `roof_between` refuses every reach, and ANY at a screened target needs the same or an adjacent position (`screen_blocks`) |
| `roof_between(a, b) -> bool` | True when exactly one of the two is AERIAL and the other is a roofed ground position (#4608). No strike crosses it, whatever the reach or delivery, even across the passable vertical edge; the route search and `move_to_position` close that edge too |
| `screen_blocks(origin, target) -> bool` | True when `target.screens_ranged` and `origin` is neither the target nor joined to it by a passable edge (#4608): a missile or ANY strike cannot come in from further away |
| `set_position_cover(position, *, roofed, screens_ranged)` | Set a live position's cover facts and drop the room's cached graph (#4608). The aerial layer is not touched: the reach and route rules read the flags directly |
| `edge_between(a, b)` | Single edge lookup, order-independent |
| `position_of(objectdb)` | Current `Position` for an object or `None` |
| `room_position_adjacency(room)` | Full ADJACENT-reach adjacency map for a room. Reads `room.positions_cached` — the Prefetch/query shared interface (`ObjectParent.positions_cached`, a `cached_property` a viewset's `Prefetch(to_attr=...)` may pre-fill); no probing, no fallback branch. |
| `edge_blocks_crossing(edge) -> bool` | The walker rule (#4606), read off the edge row alone: an active gating challenge blocks; a sealed edge with no challenge is a hard seal and blocks; a sealed edge whose challenge is no longer active is open (a climbed wall keeps `is_passable=False`); a deleted challenge (`SET_NULL`) leaves a hard seal. Reach (`position_reachable`) ignores gates. |
| `adjacent_open_positions(position)` | Edges a walker can cross from `position` (`edge_blocks_crossing`) |
| `reachable_positions(objectdb)` | Multi-hop BFS over the edges a walker can cross |
| `edge_crossing_cost(edge, traversal) -> int \| None` | The traversal rule (#4607): hops a mover of `CreatureTraversal` pays to cross an edge, None when closed. The vertical edge between a roofed position and the air above it is closed to everyone (#4608). An edge touching an AERIAL node is open to FLIES only; an open ground edge costs 1; a wall with an active gating challenge costs CLIMBS/LEAPS `GATED_CROSSING_HOPS` (2) and is closed to WALKS/FLIES; a hard seal is closed to all. |
| `find_path(origin, goal_test, *, traversal, through_barriers=False, stop_at=frozenset()) -> list[Position] \| None` | Cheapest route (Dijkstra over `edge_crossing_cost`, ties to fewer steps then lower pk) from `origin` to the first position `goal_test` accepts, origin included (`[origin]` when it already passes). Reads the room's positions and edges from the database (two queries), never the prefetched `positions_cached`/`all_edges_as_a` lists, which a long-running server can hold from before the aerial layer was built. Only a FLIES mover enters AERIAL nodes, and only through a layer already materialized (it never builds one). No capacity limit. `through_barriers` (#4609) treats a ground wall damage can bring down (`is_breakable_barrier`) as open at 1 hop: the route an NPC weighs before it bashes. `stop_at` (#4663, held ground) is a set of position pks that may end a route but are never expanded past; `path_costs_from` takes it too. |
| `step_costs(path, *, traversal, through_barriers=False) -> list[int]` | Hop cost of each step of a route, so a caller can cut it to a hop budget; `PositionError` on a step with no open edge. `through_barriers` prices a barrier-ignoring route as `find_path` does. |
| `path_costs_from(origin, *, traversal) -> dict[int, int]` | Hops from `origin` to every position a mover of `traversal` can reach, keyed by pk (#4609; the same costs `find_path` routes over). An NPC retreating measures path distance from its enemies with it. |
| `first_closed_edge(path, *, traversal) -> PositionEdge \| None` | The first edge along a route that is closed to the mover: on a barrier-ignoring route, the wall an NPC would bash (#4609). |
| `is_breakable_barrier(edge) -> bool` / `barrier_integrity(edge) -> int \| None` | Whether damage can bring the wall on an edge down (a plain conjured wall with integrity, or a Rampart's seal), and its live strength (the Rampart's integrity for a seal). A staff-authored seal is indestructible (#4609). |
| `strike_reaches(attacker_pos, target_pos, delivery) -> bool` | The reach rule by `StrikeDelivery` (#4607): MELEE = `position_reachable` ADJACENT, MISSILE = ANY, both after the cover rules (#4608: no strike across a roof, and a MISSILE at a screened target only from the same or an adjacent position); either position None = reachable (lenient); an unknown delivery is MELEE. Reads the edge from the same database-built room graph as `find_path`; callers memoize it per pass (`ReachMemo`). Used by NPC selection, advance and re-fit. |
| `aerial_layer_for_route(room)` | Context manager (#4607): builds the room's aerial layer for a flier's route search and walk when none exists, and tears it down on exit unless someone ended up airborne, so planning never leaves "Above" positions on the map. |
| `position_graph(room) -> PositionGraph` | Full node+edge graph for the tactical map (#2006) — every position and every edge (unlike `room_position_adjacency`, keeps impassable/gated edges so the UI can render them). `PositionGraph` is `{nodes: list[PositionNode], edges: list[PositionEdgeInfo]}`; `PositionNode` is `{id, name, kind, elevation_anchor_id, layout_x, layout_y, rampart_element, rampart_integrity, rampart_max_integrity, rampart_crack_state}` (the last four, #2209, are `None` on an uncovered position), `PositionEdgeInfo` is `{position_a_id, position_b_id, is_passable, blocks_flight, gating_challenge_name, integrity, max_integrity}` (the last two, #4606, read through `PositionEdge.barrier_integrity`, so a Rampart's seal shows the Rampart's pool; `None` on an indestructible edge). Since #4606 the edge shows what a walker meets: `is_passable` is the walker rule (`not edge_blocks_crossing(edge)`, so a climbed wall reads passable though its row stays sealed) and `gating_challenge_name` names only a gate that is still active. Reads `room.positions_cached` (shared interface): zero extra queries when the caller's queryset pre-filled it via `Prefetch(to_attr=...)` with edges on `all_edges_as_a` + `select_related("rampart__element_profile")` (the combat viewset does both); otherwise the lazy `ObjectParent.positions_cached` runs the same shape in 4 bounded queries (positions+rampart join, plus the three edge prefetches). Cache invalidation is targeted: `Position`/`PositionEdge` `save()`/`delete()` pop only the graph caches, and bulk mutation paths call `invalidate_position_graph_caches(room)` explicitly (never a blanket cached-property clear — the identity-mapped Room also caches live state like `scene_data`). |

*Conjured walls (#2019, #4606):*

| Function | Summary |
|----------|---------|
| `create_conjured_obstacle(a, b, *, caster_sheet, integrity, source_rampart=None, duration_rounds=None, gating_challenge=None, blocks_flight=False)` | Seal the edge (`update_or_create`, last writer wins). A caster wall passes an integer `integrity` (written to both `integrity` and `max_integrity`); a Rampart's seal passes `source_rampart` and stores no integrity; neither is a `ValueError`. Overwriting an edge takes it over (integrity, Rampart link, gate) and releases the gate it displaced. |
| `restore_edge(edge)` | The one way a wall ends: passable again, duration/caster/integrity/Rampart link/gate cleared. The gate is deactivated (never deleted) once no other edge gates on it, so a Rampart's shared challenge goes quiet with its last edge. |
| `damage_barrier(edge, chip, *, damage_type=None) -> bool` | The one mutation seam for wall integrity; True when the wall fell. A Rampart's seal routes to `damage_rampart` after the element's resist row for `damage_type` (`RampartElementProfile.base_resist`, the same term interception reads), floored at 1. A plain wall loses `chip` and is restored at 0; an indestructible edge takes nothing. Its plain-edge caller is the NPC bash step (`npc_tactics._run_bash`, #4609); a PC beats a conjured wall through its challenge. |
| `expire_obstacle_rounds(room)` / `teardown_conjured_obstacles(room)` | Per-round duration tick and scene-end teardown; both end a wall through `restore_edge`. |

**Spell walls.** `world.magic.services.effect_handlers.create_obstacle` (reached from the
Barricade marker's `create_obstacle_on_condition`) gives every spell wall integrity
`CONJURED_WALL_BASE_INTEGRITY` (10) plus the cast's power term (the marker's power-scaled
`severity`), and gates it with a fresh instance of the authored "Conjured Barrier"
`ChallengeTemplate` (`CONJURED_BARRIER_CHALLENGE_NAME`; climb over or smash through,
ADR-0109), held by the room. `world.areas.positioning.barrier_content
.ensure_conjured_barrier_content` seeds that template and its two approaches (Climb Over:
traversal vs elevated; Smash Through: force vs breakable; both on Athletics) through the
`conjured_barrier` Big Button cluster, and the Required content dashboard lists it. A
success resolves the challenge (DESTROY), which opens the wall through the walker rule.
The action list shows a sealed, gated edge as "Move to X (blocked: <challenge>)" with the
challenge's approaches beside it.

*Ramparts (#2209):*

| Function | Summary |
|----------|---------|
| `raise_rampart(position, *, caster_sheet, element_profile, integrity, duration_rounds=None, gating_challenge=None)` | Create (or replace, `update_or_create` keyed on `position`) the `Rampart` covering `position`. When `element_profile.signature_behavior == SEAL_EDGES`, also seals every `PositionEdge` touching the position via `create_conjured_obstacle(source_rampart=rampart)` — Stone is a wall, not just a ward; the sealed edges share one optional `gating_challenge` and carry no integrity of their own (#4606). |
| `rampart_at(position) -> Rampart \| None` | The `Rampart` covering a position, or `None` |
| `damage_rampart(rampart, chip) -> bool` | The single mutation seam for rampart integrity — chips `integrity` down by `chip`; at 0 opens every edge the Rampart sealed (`unseal_rampart_edges`), deletes the row (collapse) and returns `True`. Both combat interception and WARD-Clash progress sync funnel through here so the two paths never drift apart. |
| `expire_rampart_rounds(room)` | Per-round duration tick (mirrors `expire_obstacle_rounds`) — decrements `duration_rounds` on the room's ramparts, unsealing and deleting at 0; staff-authored (`duration_rounds=None`) ramparts are never decremented |
| `teardown_ramparts(room)` | Unseal and delete every `Rampart` in the room (scene end; mirrors `teardown_conjured_obstacles`). Loops the rows, since a queryset delete would skip the unseal. |
| `unseal_rampart_edges(rampart)` | `restore_edge` on every edge whose `source_rampart` is this Rampart (#4606). `Rampart.delete()` runs it first, so a collapse, an expiry, a teardown and any other single delete all open the seal (live Ramparts are not registered in the admin); `raise_rampart` runs it when a recast picks an element that does not seal. An edge a later spell took over has no link and stays sealed. `source_rampart` is `SET_NULL` only so a bulk queryset delete does not fail; an edge orphaned that way stays a hard seal, so code that deletes Ramparts loops the rows. |

*Placement + movement:*

| Function | Summary |
|----------|---------|
| `place_in_position(objectdb, position)` | Idempotent unconditional placement (staff / setup); the UNCHECKED primitive — bypasses entry-kind + mobility (#2005) |
| `take_position(objectdb, position)` | Voluntary entry onto the position graph for an UNPLACED actor — restricted to PRIMARY/FEATURE entry kinds + MOVEMENT capability (#2005) |
| `move_to_position(objectdb, target, *, traversals=frozenset({WALKS}))` | Voluntary move (#4663: `traversals` is the mover's set, from `traversal.player_traversals`; the action passes it): validates same room, current placement, adjacency, the walker rule (`edge_blocks_crossing`: an active gate answers "Crossing that requires getting past <challenge>.", a hard seal "The way is blocked."), an AERIAL target needs the `aerial` property ("You cannot fly.", #4607), no roof between the two positions ("A roof is in the way.", #4608), MOVEMENT capability. A walled edge passes when `best_crossing_cost(edge, traversals)` is not None. The validation is `check_move_to_position(objectdb, target, *, traversals)` (raises `PositionError`, changes nothing), which `move_to_position` calls before `_commit_position`, and which the held-ground pass calls before it rolls. Like `place_in_position` and `force_move_to_position` it writes through `_commit_position`, the one position writer, which also drops the identity-mapped `current_position` cache of the object's `CombatOpponent`/`CombatParticipant` rows (#4607) and, once the move commits, pings each open combat encounter in the room so its battle maps refetch (`notify_room_encounters_on_commit`, #4644) |
| `player_traversals(sheet) -> frozenset[str]` | `world/areas/positioning/traversal.py`, #4663. WALKS plus each `CapabilityType.traversal` whose `get_effective_capability_value(sheet, capability)` is above its `innate_baseline` (one query for the capability rows that name a traversal). `traversals_of(objectdb)` is the same for any object (WALKS only without a sheet) |
| `cheapest_crossing(edge, traversals) -> tuple[int, str] \| None` / `best_crossing_cost(edge, traversals) -> int \| None` | #4663. The cheapest `edge_crossing_cost` over the mover's traversals and which traversal gave it (ties go to declaration order, so CLIMBS before LEAPS); None when none crosses. The move list's "Climb over" / "Leap over" label reads it |
| `force_move_to_position(objectdb, target)` | Bypass capability + edge checks (staff/consequence) |

### Actions [BUILT & WIRED]

**`src/actions/definitions/positioning.py`**

| Action | Registry Key | Prerequisite | Notes |
|--------|-------------|--------------|-------|
| `MoveToPositionAction` | `move_to_position` | `CombatMovementPrerequisite` (#4607: in an active encounter, only while DECLARING and with a hop left; the move spends one, or the crossing cost over a wall, #4663: "That crossing takes N hops; you have M left." when short) | Dispatched with `ActionRef(registry_key="move_to_position", position_id=<pk>)`; surfaced via `get_player_actions` |
| `TakeFlightAction` | `take_flight` | `CombatMovementPrerequisite` + `CanFlyPrerequisite` ("You cannot fly." without FLIES among her traversals, "You are already in the air.", "A roof is in the way." under a roofed position) | #4663. Calls `enter_aerial`; spends one hop in a DECLARING round; no kwargs. The move list offers "Take flight" to a ground flier |
| `LandAction` | `land` | `CombatMovementPrerequisite` + `AirbornePrerequisite` ("You are not in the air.", "A roof is in the way." over a roofed anchor) | #4663. Calls `leave_aerial`; one hop in a DECLARING round; no kwargs |
| `PassHeldGroundAction` | `pass_held_ground` | `CombatMovementPrerequisite` | #4663. Kwargs `position_id`, optional `approach_id`. Rolls to get past the enemy holding an adjacent place (see "Held ground" below); costs what a walk to that place costs (1 hop, or the crossing cost over a wall) and is refused with fewer hops left |
| `TakePositionAction` | `take_position` | none | Voluntary entry for an UNPLACED actor; dispatched with `ActionRef(registry_key="take_position", position_id=<pk>)`; surfaced via `get_player_actions` for PRIMARY/FEATURE positions only (#2005) |
| `GMPlaceInPositionAction` | `gm_place_in_position` | none (gate is in-body, not a `Prerequisite`) | Staff OR active-scene GM (mirrors `_actor_may_gm_battle`; no active scene means staff-only) — wraps the unchecked `place_in_position`. `ActionRef(registry_key="gm_place_in_position", position_id=<pk>, target_object_id=<ObjectDB pk co-located with actor>)` (#2005) |
| `SetTheStageAction` | `set_the_stage` | `MinimumGMLevelPrerequisite(GMLevel.STARTING)` (staff bypass preserved, #2117) | Dispatched with `ActionRef(registry_key="set_the_stage", blueprint_id=<pk>, replace=False)`; surfaced via `get_player_actions` when the room's `RoomProfile.default_blueprint` is set. `ActionRef` carries a `blueprint_id` field for this. |

The `_set_the_stage_actions(character)` helper in `src/actions/player_interface.py` surfaces one quick-action using the room's `default_blueprint` for any actor who passes `MinimumGMLevelPrerequisite(GMLevel.STARTING)` (STARTING-tier GM trust or higher, staff bypass preserved, #2117) — the same gate `SetTheStageAction` itself enforces, so a caller who can see the quick action can always execute it.

**`_gm_place_in_position_actions(character)` (#3385)** — the analogous adapter for
`GMPlaceInPositionAction`, wired into `get_player_actions()` alongside
`_set_the_stage_actions`. Returns `[]` when `character.location is None` or
`_actor_may_gm_place(character)` (imported directly from `actions.definitions.positioning`)
is `False`; otherwise emits one `PlayerAction` per `Position` in the room, each
`ActionRef(registry_key="gm_place_in_position", position_id=<pk>)` — deliberately no
`target_object_id` on the ref, since `_dispatch_registry` merges caller-supplied `kwargs`
(including `target_object_id`) before overlaying `ref.position_id`, so the web UI supplies
the target at dispatch time.

### Telnet [BUILT & WIRED]

**`src/commands/positions.py`** — `CmdPosition` (`position`, #2005), the telnet face of the
position graph, mirroring `CmdPlaces`' shape:

- Bare `position` — lists the caller's current room's staged positions with their kind,
  occupants, and ADJACENT-reach adjacency (via `room_position_adjacency`), or reports
  `"This room has no positions staged."` when the room has none.
- `position <name>` — resolves a `Position` by name scoped to the caller's room
  (case-insensitive exact match, falling back to a unique prefix match) and calls
  `TakePositionAction().run(caller, position_id=...)` when the caller is unplaced
  (`position_of(caller) is None`), else `MoveToPositionAction().run(caller, position_id=...)`.
  Ineligible-kind, non-adjacent, and gated/immobile failures surface the action's own
  `ActionResult.message` verbatim (no separate telnet error copy).
- `position/fly`, `position/land` (#4663): dispatch `TakeFlightAction` / `LandAction`.
  `position/pass <name>` (#4663): resolves the place with `resolve_position_by_name` and
  dispatches `PassHeldGroundAction` (no `approach_id`: the best matching approach is rolled).
- `position/place <target>=<position name>` (#3385) — dispatches `GMPlaceInPositionAction`.
  `<target>` resolves via `self.caller.search(target_name, location=self.caller.location)`
  (co-located search only); `<position name>` resolves via the shared
  `resolve_position_by_name` helper (`commands/utils/gm_resolution.py`) — the same one bare
  `position <name>` uses. No gate in the command itself — the Action re-checks
  `_actor_may_gm_place` server-side regardless of what a forged dispatch claims.

Registered in `commands/default_cmdsets.py` alongside `CmdPlaces`.

**`src/commands/encounter.py`** — `CmdEncounter add <name> <tier> [pool [position]]` (#3385)
gained an optional 4th token: a position name, resolved via the same shared
`resolve_position_by_name(room, name)` helper `CmdPosition` uses
(`commands/utils/gm_resolution.py`), forwarded as `position_id` to `AddOpponentAction` —
closing telnet's gap with the web `AddOpponentDialog`, which has taken a position since #2005.

### Shared Serializers [BUILT & WIRED]

**`src/world/areas/positioning/serializers.py`** — imported by both combat and scenes layers:

| Serializer | Output |
|------------|--------|
| `PositionSummarySerializer` | `{id, name}` |
| `PersonaPositionSerializer` | `{persona_id, position: {id, name} | null}` |
| `PositionAdjacencyItemSerializer` | `{position_id, adjacent_position_ids: [int]}` |
| `PositionNodeSerializer` | `{id, name, kind, elevation_anchor_id, layout_x, layout_y, rampart_element, rampart_integrity, rampart_max_integrity, rampart_crack_state}` — tactical-map node shape (#2006; rampart fields added #2209, all four `None` when uncovered) |
| `PositionEdgeSerializer` | `{position_a_id, position_b_id, is_passable, blocks_flight, gating_challenge_name, integrity, max_integrity}` — tactical-map edge shape (#2006; wall integrity added #4606, `None` when indestructible) |

### Scene API Extension [BUILT & WIRED]

`SceneDetailSerializer` (`src/world/scenes/serializers.py`) exposes fields on the scene detail endpoint:

| Field | Type | Content |
|-------|------|---------|
| `positions` | `[{id, name}]` | All positions in the scene's room |
| `position_adjacency` | `[{position_id, adjacent_position_ids}]` | ADJACENT-reach adjacency map |
| `persona_positions` | `[{persona_id, position}]` | Per-participant position (null if unplaced) |
| `position_nodes` | `[PositionNode]` | Full tactical-map graph nodes for the scene's room, via `position_graph(obj.location)` (#2006) |
| `position_edges` | `[PositionEdgeInfo]` | Full tactical-map graph edges for the scene's room, via `position_graph(obj.location)` (#2006) |

### Combat API Extension [BUILT & WIRED]

`EncounterDetailSerializer` (`src/world/combat/serializers.py`) exposes the same two graph fields on the combat encounter detail endpoint, sourced from `position_graph(obj.room)`:

| Field | Type | Content |
|-------|------|---------|
| `position_nodes` | `[PositionNode]` | Full tactical-map graph nodes for the encounter's room (#2006) |
| `position_edges` | `[PositionEdgeInfo]` | Full tactical-map graph edges for the encounter's room (#2006) |

`Participant.current_position` / `Opponent.current_position` (both `PositionSummarySerializer` — `{id, name} | null`) locate each combatant on the graph; unlike the scene side's `persona_positions` list, combat tracks position directly on the participant/opponent row.

### Frontend [BUILT & WIRED]

- `TacticalMap` (`frontend/src/areas/components/TacticalMap.tsx`) — shared read-only `@xyflow/react` canvas rendering a Position graph: occupant avatars per node (`PositionMapNode.tsx`), edges styled by passability/gating (`edgeStyle`; a conjured wall's label carries its strength, "Conjured Barrier 7/12", #4606), click-to-move via the caller-supplied `moveActions`/`onDispatchMove`. Auto-layout (`tacticalLayout.ts`'s `computeTacticalLayout`, a pure BFS-ring placement) is used per-node when `layout_x`/`layout_y` are both null; explicit cosmetic coordinates take precedence. Dragging is disabled — coordinate authoring is out of scope for #2006. The canvas opens with `fitView` and a `minZoom` of 0.1 (React Flow's default floor of 0.5 stopped the fit at half scale, so a room wider than twice the sidebar never fit, on open or from the fit button, #4641). `PositionMapNode` also renders a rampart ring overlay when a node carries `rampart_element` (#2209): solid border when INTACT, dashed when CRACKED, faint pulsing dashed when CRUMBLING, colored by element (stone=slate, wind=sky, fire=orange, thorn=green, neutral fallback for unrecognized elements), with a `title` tooltip (`"Stone Rampart 18/24"`). Optional `onGMPlace?: (positionId) => boolean` prop (#3385) — consumed in `handleClick` right after the #2206 `onPickPosition` cast-targeting hook and before move-dispatch; a `true` return consumes the click. **Tactical overlays (#3555):** each occupant avatar can carry `marks` (`OccupantMark {kind: 'locked' | 'covering' | 'covered', title}`), rendered as small titled glyphs on the avatar, and every occupant of a node with a rampart gets a behind-cover glyph derived from the node's own `rampart_element` (a `Rampart` is deleted at zero integrity, so present means still cover). An optional `links?: OccupantLink[]` prop (`{id, positionAId, positionBId, label}`) draws an animated rose overlay edge (`link-<id>`) between two positions; a same-position pair draws no edge since both marks already sit on one node. `CombatTacticalMap` builds both from `EncounterDetail.engagement_locks` (both sides marked, link between their positions) and `current_round_actions` rows with `maneuver: 'cover'` (coverer and covered ally marked; visibility is whatever the backend's covenant/GM scoping already returns). `SceneTacticalMap` passes neither.
- `SceneTacticalMap` (`frontend/src/scenes/components/SceneTacticalMap.tsx`) — non-combat wrapper; builds `occupantsByPosition` from the scene's `persona_positions`, renders nothing when the room has no positions. Replaced the old `RoomPositionsPanel` text-list UI (#2006). GM-place picker (#3385): when `gm_place_in_position` `PlayerAction`s are present in the scene's available actions (the same "am I GM" signal `setTheStageAction` already uses — no separate prop), a "Place" toggle + target `<select>` appear above the map; targets are built from `persona_positions`' co-located personas via `character_sheet` (the persona's character ObjectDB pk); selecting a target and clicking a node dispatches `gm_place_in_position` with `target_object_id` in the kwargs.
- `CombatTacticalMap` (`frontend/src/combat/components/CombatTacticalMap.tsx`): combat wrapper; builds `occupantsByPosition` from `Participant.current_position`/`Opponent.current_position` instead of `persona_positions`. Since #4670 it renders `BattleMap` (an SVG, not `TacticalMap`) and is the main view of a fight: `CombatMainMap` mounts it in the wide column of `SceneDetailPage` and `GamePage` while an encounter is on, and `CombatRail` keeps only "Your Turn" (and "GM" for a scene GM). `CombatRail` renders in-scene on `/scenes/:id`, not a dedicated route (#2197). Same GM-place picker as `SceneTacticalMap` (#3385); targets are built from `encounter.participants` (`character_sheet_id`) and `encounter.opponents` (`objectdb_id`), both already on `EncounterDetail`.
- `MovementActions` — shared component (extracted from combat; lives in `frontend/src/combat/components/`); renders adjacent-position move buttons (a non-map fallback list still used elsewhere). Since #4663 it lists every move entry `roundActionHelpers.isMoveAction` admits (`move_to_position`, `take_flight`, `land`, `pass_held_ground`), keyed by `registry_key` and position (a step and a pass roll can name the same place), shows each entry's note (e.g. "Held by Bandit: you'd stop there.", a pass's approach) and toasts the result's message on success. `hopsLeftLine` finds the "N hops left this round." line on any move entry. On the map a click on a held place takes the plain step; the pass roll stays a panel choice.

### Movement by capability and held ground [BUILT & WIRED] (#4663, slice 2 of #4651)

**Player traversal.** `CapabilityType.traversal` (blank, or a `CreatureTraversal` value) marks a
capability as a way of moving. A character moves that way while her effective capability value is
above the row's `innate_baseline`, from a technique, condition, species, distinction or gear
(`get_effective_capability_value` folds in `CharacterModifier` rows that have not expired). The
roll for a wall's gating challenge is unchanged; what changed is that a climber or leaper's
crossing is priced and offered: the move list gives "Climb over to X (N hops)" for a gated edge
she can cross, and "Move to X (blocked: ...)" stays for a mover who cannot. Taking off and
landing are `take_flight` and `land`; both refuse under a roof, as `edge_crossing_cost` does.

**Held ground** (`world/combat/services/held_ground.py`). In a live encounter a place is held
against a mover when a ready enemy stands in it: for a PC, the places of ACTIVE ENEMY opponents;
for an ENEMY opponent, the places of ACTIVE participants who can act plus ACTIVE ALLY opponents;
for an ALLY opponent, ACTIVE ENEMY opponents (by stored `allegiance`). The mover's own place is
never held against her, so starting in held ground and leaving costs a normal hop.
`held_position_ids_against(mover)` returns the set; `encounter_holds(encounter)` returns an
`EncounterHolds` read once per planning pass, from which `against_opponent(opponent)` derives an
opponent's set. A player character is stopped however she moves on the ground (walking, climbing or leaping),
and her way past is the pass roll; only NPCs skip the roll, so an NPC walker or climber stops
and an NPC flier or leaper passes. Entering a held place stops her: a PC's `hops_used` becomes `hops_for(sheet)` and she is told "You are stopped
by <name>.". She is not stopped by ground held below her while she is in the air; landing in
a held place is an entry and stops her like any other. NPC routing uses
`routing_profile(opponent, holds)` (the opponent's `MovementProfile` with `stop_at` filled by
`npc_stop_at`), so `find_path`, `path_costs_from` and the tactics ladder treat a held place as
the end of a route. A walker whose every route is closed by held ground this round walks the
unheld route up to the first held place and goes on next round. Planning and resolution read the
same holders: `encounter_holds` takes the planning pass's PCs (`NpcRoundContext.active_participants`)
or, at resolution, the same filter (`npc_targeting._targetable_participants`: able to act and not
intangible). `held_place_holders(mover)` names who holds each place held against a PC; the move
list's "Held by <name>: you'd stop there." note (on a step and on a climb or leap alike) and
telnet's bare `position` listing ("; held by <name>") read it.

**The pass** (`world/combat/services/held_ground_pass.py`). `MovementConfig` is a singleton
(pk 1, `cached_singleton()`, admin under combat) whose `held_ground_challenge` is the
`ChallengeTemplate` rolled to get past held ground; with no row or no template no pass is
offered. `pass_choices(actor)` pairs each approach on the template whose capability the actor
holds with her strongest source for that capability, best value first; `pass_options(actor,
target)` adds the held check. `attempt_pass(actor, target, *, approach_id)` checks everything
first (live fight, the walk check `check_move_to_position`, template present, place held,
capability, approach), then inside one transaction mints the challenge instance against the
holder, resolves it with the chosen source, deactivates it, and moves her with
`force_move_to_position`. Outcome by success level: above 0 `CLEAN` ("You get past <name>."),
0 `PARTIAL` ("You get past <name>, but not cleanly."), below 0 or no check result `STOPPED`
("<name> stops you."; she is in the held place with no hops left, as after a plain walk in).
Constants: `HeldGroundPassOutcome` and the `HELD_GROUND_*` messages in
`world/combat/constants.py`; result types `PassOption` and `PassResult` in `combat/types.py`.
Refusals, in check order: "There is no fight here to get past anyone in.", the walk check's own
message, "There is no way past them.", "No one holds that place.", "You have no way past them.",
"You cannot get past them that way.".

**Authoring the pass template** (staff, `ChallengeTemplate` in admin, then set it on
`MovementConfig`). Give it an approach for each capability that should get past (acrobatics,
a flight capability, and so on). The partial outcome's consequence is whatever the template's
partial effect authors, and the challenge instance targets the holder, so a `DEAL_DAMAGE`
effect meant to hit the roller must have its target set to `self`; left on the target it
damages the holder. A `DEAL_DAMAGE` at or above `sudden_harm_interpose_threshold` (10) can be
held for an Interpose beat instead of applying at once.

**Capability sources.** `CapabilitySourceType.MODIFIER` (`world/mechanics/constants.py`):
`_get_modifier_sources` (`world/mechanics/services.py`) turns a sheet's `CharacterModifier`
rows on a capability target into one source per capability, summing live rows
(`CharacterModifierQuerySet.active()`: `expires_at` null or in the future, the one expiry rule
`get_effective_capability_value` shares). `get_available_actions` keeps one action per approach,
the one from the strongest source (`_strongest_source_per_action`, ranked by
`(prerequisite_met, value)`), so a technique and a trait that reach the same approach offer
one entry carrying the higher value.

Journeys: `src/integration_tests/test_moving_by_capability_journeys.py`,
`test_holding_ground_journeys.py`, `test_crossing_a_wall_journeys.py`; fuzz in
`integration_tests/fuzz/test_path_service_fuzz.py`.

### The battle map drawing [BUILT & WIRED] (#4670, slice 1 of #4651, ADR-4670)

The combat map is a drawing of the position graph. The place is still the rule: hops, held
ground, walls and reach read places and edges, never squares. Nothing below changes a roll,
a cost or a reach.

**Columns** (`world/areas/positioning/models.py`, migration 0297).
- `PositionNodeBase.area_x`, `area_y`, `area_w`, `area_h` (`Position` and `BlueprintPosition`):
  the rectangle a place is drawn as, in map squares. All four are set or all four are null,
  and a set width and height are at least 1 (`_area_constraint`, one `CheckConstraint` per
  table). A place with no area is drawn as a derived 3x2 area at its layout point by the
  frontend (`battleMapLayout.ts`), and takes no square.
- `PositionNodeBase.terrain`: FK to `MapTerrain`, null allowed, `SET_NULL`.
- `MapTerrain` (`name` unique, `art` FK to `Media`): a named ground look staff author in admin
  (`MapTerrainAdmin`, `world/areas/admin.py`). It is drawing only: no rule, roll or cost reads
  it.
- `ObjectPosition.square_x`, `square_y`: the square a token stands on inside the place's area.
  Both set or both null (`object_position_square_both_or_neither`). Null means the map arranges
  the token itself.
- `instantiate_blueprint` copies `area_*` and `terrain` from each `BlueprintPosition` to the live
  `Position`.

**Services** (`world/areas/positioning/services.py`).
- `validate_square(position, square, *, mover)` refuses a square the mover cannot stand on:
  "{place} has no squares to pick." (the place has no area), "That square is outside {place}.",
  "Someone is standing there." (another `ObjectPosition` holds it; the mover's own row is
  excluded).
- `place_in_position`, `take_position` and `move_to_position` take an optional `square`,
  validated before the commit. `_commit_position` stores it. Any move without a square clears
  the stored square, so a plain move never leaves a stale one.
- `step_to_square(objectdb, square)` stands the actor on another square of the place she
  already holds. It costs no hop and works in any phase. It needs the actor to be placed
  ("You aren't standing anywhere.") and able to move (`_can_move`, so a rooted or defeated actor
  cannot re-tile).
- `square_of(objectdb)` reads the stored square from the loaded `object_position`.

**Actions** (`actions/definitions/positioning.py`). `MoveToPositionAction` and
`TakePositionAction` accept `square_x` and `square_y` kwargs (both or neither, else "Pick a
square with both coordinates."; `MoveToPositionAction` validates the square before it spends a
hop). `StepToSquareAction` (key `step_to_square`) is dispatched by registry key from the map and
is not in the available-actions list. Squares have no telnet verb.

**Payload fields.**
- Each `position_nodes` entry (`PositionNodeSerializer`, scene and encounter): `area_x`,
  `area_y`, `area_w`, `area_h`, `terrain_name`, `terrain_art_url` (the terrain art's Cloudinary
  URL).
- Encounter `participants[]` and `opponents[]`: `current_square` (`{x, y}` or null).
- Encounter `held_positions[]`: `{position_id, holder_names}` for each place a ready enemy
  holds (`held_ground.enemy_held_places`). The same for every viewer, since the holders stand
  in plain sight.
- Scene `persona_positions[]`: `square_x`, `square_y` beside `position`.

**Frontend.** `BattleMap` (`frontend/src/combat/components/BattleMap.tsx`, pieces in
`battleMapPieces.tsx`, palette in `combat/battleMapPalette.ts`) is a plain SVG: place areas over
tiled terrain art, a grid, gated and impassable routes with labels, lock links, rampart rings,
held places tinted with "Held by ...", and tokens on squares. `battleMapLayout.ts` places
derived areas (`placeAreas`), fills token squares (`tokenSquares`, an occupant without a stored
square gets a free one) and computes the viewBox. A click on a square in the viewer's own place
dispatches `step_to_square`; a click on a square in another place dispatches the move with
`square_x`/`square_y`. A place with no area moves without a square.

Journeys: `src/integration_tests/test_battle_map_drawing_journeys.py`.

### Rampart — Living Barriers [BUILT & WIRED] (#2209, epic #2040 decision 3)

A `Rampart` is a projected barrier entity covering a single `Position` — see ADR-0125 for
why it's a position-anchored entity (one shared integrity pool, map-renderable crack state,
a WARD-Clash meter subject, faction-blind coverage matching ADR-0109) rather than a
`ConditionInstance` applied per-bearer. Models + services above; the cross-app pieces:

- **Interception (combat-owned).** `world.combat.services.apply_rampart_interception`
  resolves the target's `Position`, looks up its `Rampart` (`rampart_at`), and — unless a
  WARD `Clash` is already ACTIVE and bound to it (the no-double-drain rule) — chips
  `integrity` via `damage_rampart`. It runs at the very top of both damage-application
  seams, **before** the `DAMAGE_PRE_APPLY` event emits: `apply_damage_to_participant`
  (PC target) and `_resolve_opponent_pre_apply` (NPC/summon target). Firing order:
  **Rampart → personal reactive interceptors (force-field/reflect/blink) → Guardian
  reactions.** `chip = max(1, damage - resist)` (min-1 floor — a barrage always cracks a
  rampart eventually); overflow beyond remaining `integrity` passes through to the normal
  pipeline. A melee strike against a MELEE_RETALIATION (Fire) profile burns the NPC striker
  back for `signature_value`; GRASPING (Thorn) is handled at the forced-move landing seam
  instead (`force_move_to_position`), not here.
- **Strike delivery** (`StrikeDelivery`: MELEE/MISSILE, `world/combat/constants.py` — also
  the field the wind-as-mechanic combat consumer reads, #1555/ADR-0129, see
  `docs/systems/INDEX.md`'s "Combat" section) and `is_area` (`targeting_mode != SINGLE`) feed
  a Wind (MISSILE_WARD) profile's resist adjustment: bonus against MISSILE, penalty against
  area strikes.
- **WARD Clash meter sync.** `Clash.rampart` (nullable FK) binds a sustained-attack WARD
  clash to the covered position's `Rampart`; `world.combat.clash._sync_rampart_progress`
  mirrors each round's progress delta onto `rampart.integrity` via the same
  `damage_rampart` seam (a decrease drains it; an increase strengthens it, capped at
  `max_integrity`), so interception and clash-progress never drift apart.
- **Palette content** (`world.magic.effect_palette_content.ensure_rampart_content`) seeds
  the four elemental `RampartElementProfile` rows (Stone/seal_edges, Wind/missile_ward,
  Fire/melee_retaliation, Thorn/grasping) with their `RampartElementResistance` rows, plus
  one "Raise Rampart (\<Element\>)" Technique + FlowDefinition + TriggerDefinition + marker
  `ConditionTemplate` per element (Thorn also seeds the "Entangled" condition its GRASPING
  behavior applies). `raise_rampart_on_condition`
  (`world.magic.services.effect_handlers`) is the `CONDITION_APPLIED` adapter that reads
  the cast destination and calls `raise_rampart`.
- **Lifecycle.** `expire_rampart_rounds`/`teardown_ramparts` ride the same per-round tick
  and scene-end teardown as conjured obstacles (`world.vitals.services`,
  `world.scenes.scene_admin_services`).

### Exceptions

```python
from world.areas.positioning.exceptions import PositionError, PositionTransitionError
```

`PositionTransitionError` (subclass of `PositionError`) carries `user_message` for move failures; actions surface it directly.

### Aerial and Chasm Vertical Layer [BUILT & WIRED]

**`src/world/areas/positioning/services.py`**

The vertical layer adds a two-tier depth model on top of the ground graph.

**AERIAL layer (flight):**

Each non-AERIAL position in a room has an AERIAL twin named `"Above <name>"` with
`elevation_anchor` pointing to its ground counterpart.  Vertical edges connect each ground
position to its twin.  Horizontal edges in the aerial layer mirror the ground adjacency graph
but are all passable and ungated, so airborne objects fly over walls, locked gates, and chasm
edges that would block ground movement.

| Function | Summary |
|----------|---------|
| `materialize_aerial_layer(room)` | Build the full AERIAL twin graph over every ground position (idempotent; no-op when already present). Ends by dropping every in-room position's cached edge lists (`invalidate_position_graph_caches`), so a map or route read after it sees the new edges (#4607) |
| `teardown_aerial_layer(room)` | Delete all AERIAL positions in the room (cascades edges + occupancy); called when the last airborne occupant lands |
| `enter_aerial(objectdb)` | Move `objectdb` to the AERIAL twin above its current ground position; materializes the layer if needed, and draws a twin (a vertical edge plus aerial edges over neighbours whose edge does not block flight) for a ground position staged after the layer was built (#4663, `_aerial_twin`); sets the `"aerial"` `ObjectProperty` on the object |
| `leave_aerial(objectdb)` | Return `objectdb` to its `elevation_anchor` ground position; clears the `"aerial"` property; tears down the layer when no AERIAL node retains occupants. The voluntary, soft landing |
| `ground_flier(objectdb, *, allow_catch=True) -> int \| None` | `plummet.py`, #4608. Knock a flier out of the air: no-op unless it stands on an AERIAL position; clears the `"aerial"` property and hands it to `begin_plummet` from there, so it falls (catch window for a character with someone present; `allow_catch=False`, a combat opponent, lands at once). Returns the impact damage when the fall resolved in the call. `REMOVE_FLIGHT` calls it; for an opponent the handler applies the returned damage to its health (`apply_damage_to_opponent`, fall damage type, no source, soak bypassed) |

The `"aerial"` `Property` (value=1) is the runtime tag: while present, `objectdb` is
airborne.  `AerialPropertyFactory` in `src/world/mechanics/factories.py` provides the
seed/test factory for this property row (get-or-create by name).

**CHASM (below-ground vertical drop):**

A `CHASM` position is a below-ground region reached by falling.  Its `elevation_anchor`
points to the ground position above it.  Entering a CHASM — via a consequence effect or a
direct `force_move_to_position` — calls `maybe_emit_fall`, which emits `EventName.FELL`
(`FallEvent(faller, position)`) into the reactive layer.

| Function | Summary |
|----------|---------|
| `maybe_emit_fall(objectdb, position)` | Emit `EventName.FELL` when `position.kind == CHASM`; idempotently installs the room-owned `fall_to_plummet` trigger first (so the consumer is always present at the fall choke point), then emits. Returns `True` if the event was emitted, `False` otherwise |

**FELL consumer (`world/areas/positioning/plummet.py`, #1228).** A room-owned system
trigger (`fall_to_plummet`, `source_condition=None`) dispatches `EventName.FELL` to
`begin_plummet_handler` via a CALL_SERVICE_FUNCTION flow step. `begin_plummet(faller,
position, *, allow_catch=True) -> int | None` applies the seeded `Plummeting` condition, then
branches on whether anyone is present who could catch the faller (`_potential_catcher_present`
— a non-faller in the room who `can_act`; `allow_catch=False` skips the catch window, #4608).
It returns the impact damage when the fall resolved in the call, and a faller that drops out
of the air takes the empty aerial layer down as a landing does (`_settle_aerial_layer`):

- **a potential catcher is present** → instantiate the seeded **"Catch the Faller"**
  `ChallengeInstance` bound to the faller via `target_object` and ensure an AFK-safe STRICT
  `SceneRound(start_reason=DANGER)` with present characters enrolled
  (`ensure_round_for_acute_condition`). The descent then advances one level per round
  resolution (below), keeping the catch window open;
- **nobody present to catch** → the fall is environmental and self-completing, so it is
  **resolved immediately** to the floor + impact in this call (`_descend_to_floor`) rather
  than freezing in a danger round nothing will drive (ADR-0004: action-driven tempo, no wall
  clock). A falling character is **never paused mid-air** (#1479).

`begin_plummet` is idempotent — a no-op when the faller already carries the Plummeting
condition. The trigger definition is seeded by `wire_fall_triggers()` (positioning
factories); `install_fall_triggers(room)` installs it (called from `maybe_emit_fall`). The
bystander catch resolution (Task 7) is below.

**Per-round descent + impact (`plummet.py`, #1228, Task 6).** `advance_plummet(targets)`
is wired into the END-OF-ROUND block of `tick_round_for_targets` (`world/vitals/services.py`),
beside `advance_bleed_out` / `tick_fatigue_collapse_for_targets`. For each target carrying
the Plummeting condition it walks one `elevation_anchor` level down via `force_move_to_position`
and accumulates depth on the `Plummeting` `ConditionInstance.severity` (one per round — the
standard severity→consequence scaling). The round the target lands on solid ground (the new
position's `elevation_anchor is None`) `_apply_fall_impact` fires: `damage = severity *
settings.FALL_IMPACT_PER_LEVEL` (env-backed config, default 5). It **debits the faller's
`CharacterVitals.health` by that damage first** (the same order as `_apply_round_tick_damage`
/ combat's `_apply_damage` — `process_damage_consequences` resolves wound/death/knockout
tiers but does not itself debit health), then routes the same magnitude through
`process_damage_consequences` with the `Fall` `DamageType` (null pools → config-default
survivability). Both steps no-op gracefully for a faller without a `CharacterVitals` row. `end_plummet(faller, *, caught=False)` then removes the Plummeting condition
and deactivates the bound catch `ChallengeInstance`. `caught` is **not inert** — it selects
the terminal room narration via `_narrate_plummet_end` (relieved safe-landing line when
`caught=True`, grim impact line when `caught=False`), so the catch path (no impact) reads
differently from the floor impact. The descent is **AFK-safe**: empty
`tick_round_for_targets` targets ⇒ no tick ⇒ no descent. The danger round is an ordinary
STRICT round (#1466): the descent advances at round resolution (presence-gated
`maybe_resolve_scene_round`), and `_danger_persists` (`world/scenes/round_services.py`),
checked in `resolve_scene_round`, keeps the round going while any participant is Bleeding-Out
**or** Plummeting — the round auto-ends (COMPLETED) once the fall resolves.

**Bystander catch resolution (`plummet.py`, #1228, Task 7).** A bystander with a qualifying
catch capability resolves the faller's catch challenge. The catch reuses existing machinery —
no new dispatch surface: `dispatch_catch(catcher, faller, *, approach)` calls
`get_available_actions(catcher, location)` (which surfaces only the catch approaches the
catcher's capabilities qualify for — a catcher with no catch capability gets nothing, so it
raises `LookupError`), selects the catch action bound to the faller, resolves it directly via
`resolve_challenge` (a synchronous immediate-challenge call — `dispatch_catch` bypasses the
round-declaration seam entirely, so it resolves now regardless of the round's mode), then
translates the graded outcome through `resolve_catch(faller, catcher, resolution_result)`:

- **clean catch** (a SUCCESS check outcome, or any `ResolutionType.DESTROY` resolution): set
  the faller down on the catcher's safe non-CHASM position, or — when the catcher is themselves
  in a CHASM and has none — fall back to the room's PRIMARY ground (`_primary_landing_for`,
  mirroring `leave_aerial`'s ground fallback), then `end_plummet`. `caught` reflects whether the
  faller was actually placed, so a caught faller is never left in the pit while the narration
  claims a safe landing (#1284);
- **partial** (a neutral / zero-success outcome that did not destroy the challenge): soften —
  decrement the accumulated `Plummeting` `ConditionInstance.severity` (floored at 0) — but let
  the descent continue;
- **failure** (a negative outcome): no-op; the plummet continues.

**Plummet is exempt from the #1479 bleed-out hold/abandonment.** Falling is environmental, so
the descent **always advances** — it must never be paused mid-air waiting for "who is menacing
you":

- `resolve_scene_round` exempts plummeting participants (`_plummeting_character_ids`) from the
  #1480 AFK own-peril skip, so the descent advances on every END tick regardless of who drove
  the round;
- `world.vitals.peril_resolution.acute_peril_condition_names()` (the HOLD/ABANDONMENT
  classification) is **BLEED_OUT only** — a plummeting victim is never a "held downed victim,"
  is never `abandoned_since_round`-marked, and is never resolved through an abandonment
  consequence pool (`resolve_abandonment` / `resolve_solo_abandoned_victims` skip it). This is
  deliberately narrower than `_danger_persists`, which still keys a DANGER round on Bleeding-Out
  **or** Plummeting so the round keeps ticking the descent until impact;
- when a departure removes the last potential catcher, `Room.at_object_leave` calls
  `resolve_unattended_plummets(room, departing=)`, which descends any now-unattended faller to
  the floor + impact immediately (the gravity counterpart to `resolve_solo_abandoned_victims`,
  which handles bleed-out via the abandonment pool). An impact-caused bleed-out then follows the
  normal bleed-out hold/abandonment rules — only the fall itself is exempt.

**Plummet + catch content seed (`world/areas/positioning/plummet_content.py`).**
`ensure_fall_content()` idempotently seeds all plummet + catch content (it calls
`ensure_catch_content()`); it runs in production via the `reactive_challenges`
cluster in `world.seeds.clusters` (#2636), alongside the Interpose/Succor/redirect
siblings:

- the `Fall` `DamageType` (null pools → config-default survivability) and the `Plummeting`
  `ConditionTemplate` — a simple non-progressive, `PERMANENT`-duration marker (no stages,
  no DoT). Depth is tracked solely by the instance's per-round `severity` accumulator
  (`advance_plummet` does `severity += 1` per level descended), which feeds the impact
  `damage = severity * FALL_IMPACT_PER_LEVEL`. `PERMANENT` keeps the descent loop the sole
  authority over its lifetime: the end-of-round duration countdown never expires it mid-air,
  so deep falls always reach impact — only `advance_plummet`/`end_plummet` remove it;
- the capability-gated **"Catch the Faller"** `ChallengeTemplate` (authored `severity` on
  the row). Its approaches are gated by catch capabilities — the seed examples are the four
  `CapabilityType` rows `fly` / `teleport` / `telekinesis` / `acrobatics`. Every catch
  `Application` shares one target `Property` (`catchable`, linked to the template so the
  approaches surface in `_match_approaches`), and every `ChallengeApproach` reuses one
  `Reflexes` `CheckType`. A SUCCESS-tier `ResolutionType.DESTROY` consequence resolves the
  challenge on a clean catch.

Adding a new catch capability is **pure data** — one `CapabilityType` +
`Application(target_property=catchable)` + `ChallengeApproach` row, with zero engine code.
Identity-key names live in `world/areas/positioning/constants.py`.

**Gated-edge crossing and `MOVE_TO_POSITION`:**

A gated `PositionEdge` (`gating_challenge` IS NOT NULL, and its `gating_challenge.is_active`
is True on the `ChallengeInstance`) blocks `move_to_position` for normal traversal.  Players who approach via a `ChallengeApproach`
using `PERSONAL` resolution mode cross the gate for themselves only (the
`ChallengeInstance` remains active for other characters).  A `MOVE_TO_POSITION` /
`GATING_FAR_SIDE` `ConsequenceEffect` on the approach's consequence pool executes
`force_move_to_position` to the far side; `_gating_far_side()` in
`world/mechanics/effect_handlers.py` resolves the far side from the edge whose
`gating_challenge` matches the active `ChallengeInstance`.  Gated edges appear as locked
entries in the player's move list until the gating challenge is resolved.

Blueprint-authored gated edges work the same way as hand-authored ones:
`BlueprintEdge.gating_challenge_template` + `instantiate_challenge` mint the live
`ChallengeInstance` on staging, so an instantiated blueprint's gated edges block
`move_to_position` identically to a gate authored directly on a room's `Position` graph.

### Deferred (follow-up required)

- **Reactive fall catch + multi-round plummet (built — #1228):** `EventName.FELL` is consumed
  by `begin_plummet` (`plummet.py`), which ensures the STRICT danger round, applies `Plummeting`, and
  binds the catch challenge to the faller (Task 5); `advance_plummet` walks the descent down
  the `elevation_anchor` chain with impact consequences in the round tick (Task 6); and
  `dispatch_catch` → `resolve_catch` lets a capability-gated bystander catch the faller —
  clean catch ends the plummet with no impact and places the faller safely (Task 7). The whole
  #1228 series is now built.
- **Anti-air "blocks-flight" gate flag:** a future `PositionEdge` flag (or Property tag)
  that prevents `enter_aerial` from crossing above a blocked node.
- Zone-aware targeting (#533), POV visibility (#531), combat-UI positioning rendering (#532)
- Occupancy-screening reachability (crowded-position filtering)
- **World-builder completeness (#3269) — all three phases shipped** (Phase A:
  relational dig + recoverability + navigation/search, ADR-0219/0220; Phase B: the
  full room-authoring set + durable grid-bundle export of places/emits/hubs/
  functionaries/features/blueprint refs; Phase C: area metadata + the ward
  arrange canvas). Deliberately NOT built: staff authoring for VAULT (founder-
  persona-owned) and ward/alarm defenses (their own seam), travel routes/methods
  and Realm/Climate catalogs (admin/content-owned prerequisites), and
  BlueprintPosition/Edge canvas editing (rows round-trip as content; authoring
  stays admin).
