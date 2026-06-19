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
| `Area` (SharedMemoryModel) | A spatial hierarchy node at a specific level | `name`, `level` (AreaLevel), `parent` (self-FK), `realm` (FK to `realms.Realm`), `description` |
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
)
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
| `Position` | Named tactical region in a room | `room` FK → `objects.ObjectDB`; unique per room+name; `elevation_anchor` (self-referential FK → `Position`, null=floor/top-level) — the ground `Position` this AERIAL or CHASM node is anchored to (**omitted from `MODEL_MAP.md`** — the auto-generation tool skips self-referential FKs) |
| `PositionEdge` | Traversable adjacency between two `Position` nodes | `position_a` / `position_b` FK (canonical pk order); `is_passable`; `gating_challenge` FK → `mechanics.ChallengeInstance` (nullable) |
| `ObjectPosition` | One-to-one occupancy record | `objectdb` OneToOne PK; `position` FK — mirrors `db_location` |

**Blueprint template graph** (room-independent):

| Model | Purpose | Key Fields / Constraints |
|-------|---------|--------------------------|
| `PositionBlueprint` | GM-authored reusable terrain layout | `name` (unique), `description` |
| `BlueprintPosition` | Position node template inside a blueprint | `blueprint` FK; name unique per blueprint |
| `BlueprintEdge` | Edge template inside a blueprint | `blueprint` FK; `position_a` / `position_b` FK → `BlueprintPosition` (canonical pk order); `is_passable` |

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
| `connect_blueprint_positions(a, b, *, is_passable)` | Create a `BlueprintEdge` (raises `PositionError` for cross-blueprint) |
| `remove_blueprint(blueprint)` | Delete blueprint and its positions/edges (cascade) |

*Staging:*

| Function | Summary |
|----------|---------|
| `instantiate_blueprint(blueprint, room, *, replace=False)` | Clone a blueprint's position graph into a room (returns new `Position` list). Raises `PositionError` if already staged and `replace=False`; raises `PositionError` if occupied when `replace=True`. Runs atomically. |

*Query:*

| Function | Summary |
|----------|---------|
| `position_reachable(origin, target, reach)` | Reach-semantics check (SAME / ADJACENT / ANY) |
| `edge_between(a, b)` | Single edge lookup, order-independent |
| `position_of(objectdb)` | Current `Position` for an object or `None` |
| `room_position_adjacency(room)` | Full ADJACENT-reach adjacency map for a room (uses prefetched attrs when available) |
| `adjacent_open_positions(position)` | Edges to passable, non-actively-gated neighbors |
| `reachable_positions(objectdb)` | Multi-hop BFS over passable, non-gated edges |

*Placement + movement:*

| Function | Summary |
|----------|---------|
| `place_in_position(objectdb, position)` | Idempotent unconditional placement (staff / setup) |
| `move_to_position(objectdb, target)` | Voluntary move — validates same room, current placement, adjacency, passability, gating challenge, MOVEMENT capability |
| `force_move_to_position(objectdb, target)` | Bypass capability + edge checks (staff/consequence) |

### Actions [BUILT & WIRED]

**`src/actions/definitions/positioning.py`**

| Action | Registry Key | Prerequisite | Notes |
|--------|-------------|--------------|-------|
| `MoveToPositionAction` | `move_to_position` | none | Dispatched with `ActionRef(registry_key="move_to_position", position_id=<pk>)`; surfaced via `get_player_actions` |
| `SetTheStageAction` | `set_the_stage` | `StaffOnlyPrerequisite` | Dispatched with `ActionRef(registry_key="set_the_stage", blueprint_id=<pk>, replace=False)`; surfaced via `get_player_actions` when the room's `RoomProfile.default_blueprint` is set. `ActionRef` carries a `blueprint_id` field for this. |

The `_set_the_stage_actions(character)` helper in `src/actions/player_interface.py` surfaces one quick-action using the room's `default_blueprint` for staff.

### Shared Serializers [BUILT & WIRED]

**`src/world/areas/positioning/serializers.py`** — imported by both combat and scenes layers:

| Serializer | Output |
|------------|--------|
| `PositionSummarySerializer` | `{id, name}` |
| `PersonaPositionSerializer` | `{persona_id, position: {id, name} | null}` |
| `PositionAdjacencyItemSerializer` | `{position_id, adjacent_position_ids: [int]}` |

### Scene API Extension [BUILT & WIRED]

`SceneDetailSerializer` (`src/world/scenes/serializers.py`) exposes three additional fields on the scene detail endpoint:

| Field | Type | Content |
|-------|------|---------|
| `positions` | `[{id, name}]` | All positions in the scene's room |
| `position_adjacency` | `[{position_id, adjacent_position_ids}]` | ADJACENT-reach adjacency map |
| `persona_positions` | `[{persona_id, position}]` | Per-participant position (null if unplaced) |

### Frontend [BUILT & WIRED]

- `MovementActions` — shared component (extracted from combat; lives in `frontend/src/combat/components/`); renders adjacent-position move buttons.
- `RoomPositionsPanel` — scene detail component (`frontend/src/scenes/components/`); renders positions, persona placement, the move action, and a staff "Set the stage" control using the scene's positions payload.

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
| `maybe_emit_fall(objectdb, position)` | Emit `EventName.FELL` when `position.kind == CHASM`; returns `True` if the event was emitted, `False` otherwise |

The reactive catch consumer (capability-based fly/acrobatics interrupt + AFK-safe
multi-round plummet down the `elevation_anchor` chain with impact consequences) is deferred
to a follow-up tied to the round/turn framework (#520).

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

### Deferred (follow-up required)

- **Gated blueprint edges:** `BlueprintEdge` has no `gating_challenge` analogue; when a
  blueprint is instantiated the `instantiate_blueprint` service skips gating. Full
  gated-edge instantiation requires the absent `instantiate_situation()` service (which
  mints `ChallengeInstance`s). Tracked as a follow-up to #1017.
- **Reactive fall catch + multi-round plummet:** `EventName.FELL` is emitted; the consumer
  (fly/teleport/acrobatics interrupt, AFK-safe plummet down the `elevation_anchor` chain
  with impact consequences) is deferred to the round/turn framework follow-up (#520).
- **Anti-air "blocks-flight" gate flag:** a future `PositionEdge` flag (or Property tag)
  that prevents `enter_aerial` from crossing above a blocked node.
- Zone-aware targeting (#533), POV visibility (#531), combat-UI positioning rendering (#532)
- Occupancy-screening reachability (crowded-position filtering)
