# Areas System

Spatial hierarchy for organizing rooms into buildings, neighborhoods, wards, cities, regions, kingdoms, continents, worlds, and planes.

**Source:** `src/world/areas/`

---

## Enums (constants.py)

```python
from world.areas.constants import AreaLevel
# BUILDING(10), NEIGHBORHOOD(20), WARD(30), CITY(40), REGION(50),
# KINGDOM(60), CONTINENT(70), WORLD(80), PLANE(90)
```

---

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Area` (SharedMemoryModel) | A spatial hierarchy node at a specific level | `name`, `level` (AreaLevel), `parent` (self-FK), `realm` (FK to `realms.Realm`), `description`, `grid_x`/`grid_y` (nullable, parent-local rendering coordinates, #2223) |
| `AreaClosure` | Read-only materialized view for transitive closure | `ancestor` (FK), `descendant` (FK), `depth` |

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
from world.areas.services import get_ancestry, get_ancestor_at_level, get_effective_realm
from world.areas.constants import AreaLevel

# Get full ancestry (single indexed query via materialized view)
ancestry = get_ancestry(market_area)
# Returns: [Plane, World, Continent, Kingdom, Region, City, Ward, Market District]

# Find the city this area belongs to
city = get_ancestor_at_level(market_area, AreaLevel.CITY)

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
| `PositionNodeBase` | `name`, `kind` (`PositionKind`), `description` — shared by `Position` and `BlueprintPosition` |
| `PositionEdgeBase` | `is_passable`; `_validate_canonical()` helper (self-loop + pk-ascending canonical-order) — shared by `PositionEdge` and `BlueprintEdge` |

**Live room graph** (room-anchored):

| Model | Purpose | Key Fields / Constraints |
|-------|---------|--------------------------|
| `Position` | Named tactical region in a room | `room` FK → `objects.ObjectDB`; unique per room+name; `elevation_anchor` (self-referential FK → `Position`, null=floor/top-level) — the ground `Position` this AERIAL or CHASM node is anchored to (**omitted from `MODEL_MAP.md`** — the auto-generation tool skips self-referential FKs); `layout_x`/`layout_y` (nullable small integers) — cosmetic tactical-map coordinates (#2006); `null` on both means "let the frontend auto-layout" (`computeTacticalLayout`'s BFS-ring placement) rather than "place at the origin" |
| `PositionEdge` | Traversable adjacency between two `Position` nodes | `position_a` / `position_b` FK (canonical pk order); `is_passable`; `blocks_flight` — obstructs AERIAL-layer traversal; `gating_challenge` FK → `mechanics.ChallengeInstance` (nullable) |
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
| `position_reachable(origin, target, reach)` | Reach-semantics check (SAME / ADJACENT / ANY) |
| `edge_between(a, b)` | Single edge lookup, order-independent |
| `position_of(objectdb)` | Current `Position` for an object or `None` |
| `room_position_adjacency(room)` | Full ADJACENT-reach adjacency map for a room. Reads `room.positions_cached` — the Prefetch/query shared interface (`ObjectParent.positions_cached`, a `cached_property` a viewset's `Prefetch(to_attr=...)` may pre-fill); no probing, no fallback branch. |
| `adjacent_open_positions(position)` | Edges to passable, non-actively-gated neighbors |
| `reachable_positions(objectdb)` | Multi-hop BFS over passable, non-gated edges |
| `position_graph(room) -> PositionGraph` | Full node+edge graph for the tactical map (#2006) — every position and every edge (unlike `room_position_adjacency`, keeps impassable/gated edges so the UI can render them). `PositionGraph` is `{nodes: list[PositionNode], edges: list[PositionEdgeInfo]}`; `PositionNode` is `{id, name, kind, elevation_anchor_id, layout_x, layout_y, rampart_element, rampart_integrity, rampart_max_integrity, rampart_crack_state}` (the last four, #2209, are `None` on an uncovered position), `PositionEdgeInfo` is `{position_a_id, position_b_id, is_passable, blocks_flight, gating_challenge_name}`. Reads `room.positions_cached` (shared interface): zero extra queries when the caller's queryset pre-filled it via `Prefetch(to_attr=...)` with edges on `all_edges_as_a` + `select_related("rampart__element_profile")` (the combat viewset does both); otherwise the lazy `ObjectParent.positions_cached` runs the same shape in 4 bounded queries (positions+rampart join, plus the three edge prefetches). Cache invalidation is targeted: `Position`/`PositionEdge` `save()`/`delete()` pop only the graph caches, and bulk mutation paths call `invalidate_position_graph_caches(room)` explicitly (never a blanket cached-property clear — the identity-mapped Room also caches live state like `scene_data`). |

*Ramparts (#2209):*

| Function | Summary |
|----------|---------|
| `raise_rampart(position, *, caster_sheet, element_profile, integrity, duration_rounds=None, gating_challenge=None)` | Create (or replace, `update_or_create` keyed on `position`) the `Rampart` covering `position`. When `element_profile.signature_behavior == SEAL_EDGES`, also seals every `PositionEdge` touching the position via `create_conjured_obstacle` — Stone is a wall, not just a ward. |
| `rampart_at(position) -> Rampart \| None` | The `Rampart` covering a position, or `None` |
| `damage_rampart(rampart, chip) -> bool` | The single mutation seam for rampart integrity — chips `integrity` down by `chip`; deletes the row (collapse) at 0 and returns `True`. Both combat interception and WARD-Clash progress sync funnel through here so the two paths never drift apart. |
| `expire_rampart_rounds(room)` | Per-round duration tick (mirrors `expire_obstacle_rounds`) — decrements `duration_rounds` on the room's ramparts, deleting at 0; staff-authored (`duration_rounds=None`) ramparts are never decremented |
| `teardown_ramparts(room)` | Delete every `Rampart` in the room (scene end; mirrors `teardown_conjured_obstacles`) |

*Placement + movement:*

| Function | Summary |
|----------|---------|
| `place_in_position(objectdb, position)` | Idempotent unconditional placement (staff / setup); the UNCHECKED primitive — bypasses entry-kind + mobility (#2005) |
| `take_position(objectdb, position)` | Voluntary entry onto the position graph for an UNPLACED actor — restricted to PRIMARY/FEATURE entry kinds + MOVEMENT capability (#2005) |
| `move_to_position(objectdb, target)` | Voluntary move — validates same room, current placement, adjacency, passability, gating challenge, MOVEMENT capability |
| `force_move_to_position(objectdb, target)` | Bypass capability + edge checks (staff/consequence) |

### Actions [BUILT & WIRED]

**`src/actions/definitions/positioning.py`**

| Action | Registry Key | Prerequisite | Notes |
|--------|-------------|--------------|-------|
| `MoveToPositionAction` | `move_to_position` | none | Dispatched with `ActionRef(registry_key="move_to_position", position_id=<pk>)`; surfaced via `get_player_actions` |
| `TakePositionAction` | `take_position` | none | Voluntary entry for an UNPLACED actor; dispatched with `ActionRef(registry_key="take_position", position_id=<pk>)`; surfaced via `get_player_actions` for PRIMARY/FEATURE positions only (#2005) |
| `GMPlaceInPositionAction` | `gm_place_in_position` | none (gate is in-body, not a `Prerequisite`) | Staff OR active-scene GM (mirrors `_actor_may_gm_battle`; no active scene means staff-only) — wraps the unchecked `place_in_position`. `ActionRef(registry_key="gm_place_in_position", position_id=<pk>, target_object_id=<ObjectDB pk co-located with actor>)` (#2005) |
| `SetTheStageAction` | `set_the_stage` | `MinimumGMLevelPrerequisite(GMLevel.STARTING)` (staff bypass preserved, #2117) | Dispatched with `ActionRef(registry_key="set_the_stage", blueprint_id=<pk>, replace=False)`; surfaced via `get_player_actions` when the room's `RoomProfile.default_blueprint` is set. `ActionRef` carries a `blueprint_id` field for this. |

The `_set_the_stage_actions(character)` helper in `src/actions/player_interface.py` surfaces one quick-action using the room's `default_blueprint` for any actor who passes `MinimumGMLevelPrerequisite(GMLevel.STARTING)` (STARTING-tier GM trust or higher, staff bypass preserved, #2117) — the same gate `SetTheStageAction` itself enforces, so a caller who can see the quick action can always execute it.

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

Registered in `commands/default_cmdsets.py` alongside `CmdPlaces`.

### Shared Serializers [BUILT & WIRED]

**`src/world/areas/positioning/serializers.py`** — imported by both combat and scenes layers:

| Serializer | Output |
|------------|--------|
| `PositionSummarySerializer` | `{id, name}` |
| `PersonaPositionSerializer` | `{persona_id, position: {id, name} | null}` |
| `PositionAdjacencyItemSerializer` | `{position_id, adjacent_position_ids: [int]}` |
| `PositionNodeSerializer` | `{id, name, kind, elevation_anchor_id, layout_x, layout_y, rampart_element, rampart_integrity, rampart_max_integrity, rampart_crack_state}` — tactical-map node shape (#2006; rampart fields added #2209, all four `None` when uncovered) |
| `PositionEdgeSerializer` | `{position_a_id, position_b_id, is_passable, blocks_flight, gating_challenge_name}` — tactical-map edge shape (#2006) |

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

- `TacticalMap` (`frontend/src/areas/components/TacticalMap.tsx`) — shared read-only `@xyflow/react` canvas rendering a Position graph: occupant avatars per node (`PositionMapNode.tsx`), edges styled by passability/gating (`edgeStyle`), click-to-move via the caller-supplied `moveActions`/`onDispatchMove`. Auto-layout (`tacticalLayout.ts`'s `computeTacticalLayout`, a pure BFS-ring placement) is used per-node when `layout_x`/`layout_y` are both null; explicit cosmetic coordinates take precedence. Dragging is disabled — coordinate authoring is out of scope for #2006. `PositionMapNode` also renders a rampart ring overlay when a node carries `rampart_element` (#2209): solid border when INTACT, dashed when CRACKED, faint pulsing dashed when CRUMBLING, colored by element (stone=slate, wind=sky, fire=orange, thorn=green, neutral fallback for unrecognized elements), with a `title` tooltip (`"Stone Rampart 18/24"`).
- `SceneTacticalMap` (`frontend/src/scenes/components/SceneTacticalMap.tsx`) — non-combat wrapper; builds `occupantsByPosition` from the scene's `persona_positions`, renders nothing when the room has no positions. Replaced the old `RoomPositionsPanel` text-list UI (#2006).
- `CombatTacticalMap` (`frontend/src/combat/components/CombatTacticalMap.tsx`) — combat wrapper; builds `occupantsByPosition` from `Participant.current_position`/`Opponent.current_position` instead of `persona_positions`. Mounted as a "Map" tab in `CombatRail`'s right rail, alongside the existing "Your Turn" tab (`CombatTurnPanel`) — tab defaults to "Your Turn" (#2006). `CombatRail` renders in-scene on `/scenes/:id`, not a dedicated route (#2197).
- `MovementActions` — shared component (extracted from combat; lives in `frontend/src/combat/components/`); renders adjacent-position move buttons (a non-map fallback list still used elsewhere).

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
| `materialize_aerial_layer(room)` | Build the full AERIAL twin graph over every ground position (idempotent; no-op when already present) |
| `teardown_aerial_layer(room)` | Delete all AERIAL positions in the room (cascades edges + occupancy); called when the last airborne occupant lands |
| `enter_aerial(objectdb)` | Move `objectdb` to the AERIAL twin above its current ground position; materializes the layer if needed; sets the `"aerial"` `ObjectProperty` on the object |
| `leave_aerial(objectdb)` | Return `objectdb` to its `elevation_anchor` ground position; clears the `"aerial"` property; tears down the layer when no AERIAL node retains occupants |

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
position)` applies the seeded `Plummeting` condition, then branches on whether anyone is
present who could catch the faller (`_potential_catcher_present` — a non-faller in the room
who `can_act`):

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
