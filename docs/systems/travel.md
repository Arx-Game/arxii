# Overworld Travel / Voyages

Data-driven route network connecting hub rooms. Players voyage through hubs, paying AP per leg based on travel time (distance ÷ speed). Group travel via Voyage model with per-participant AP. Arrive-on-demand lets players fast-forward to their destination if they can afford the remaining AP.

**Source:** `src/world/travel/`

---

## Models

### TravelHub (`SharedMemoryModel`)

Tags a room as a travel hub or embarkation point. OneToOne to RoomProfile.

| Field | Type | Description |
|-------|------|-------------|
| `room_profile` | OneToOneField(RoomProfile, PK) | The room this hub is |
| `name` | CharField(200) | Display name |
| `description` | TextField | Flavor text on arrival |
| `travel_modes` | JSONField(list) | List of TravelMode values (e.g. `["LAND", "SEA"]`) |
| `is_transit_stop` | BooleanField | If True, appears as waypoint in route BFS. If False, embarkation-only. |
| `is_active` | BooleanField | Staff can deactivate |

### TravelRoute (`SharedMemoryModel`)

A directed edge in the overworld route graph.

| Field | Type | Description |
|-------|------|-------------|
| `origin_hub` | FK(TravelHub) | Starting hub |
| `destination_hub` | FK(TravelHub) | Ending hub |
| `distance` | PositiveIntegerField | Abstract distance units |
| `travel_mode` | CharField(TravelMode) | LAND, SEA, or AIR |
| `is_bidirectional` | BooleanField | If True, travel works both directions |
| `difficulty_modifier` | FloatField | Multiplier on travel time (mountain pass = 1.5) |
| `name` | CharField(200, blank) | Optional display name |
| `is_active` | BooleanField | Staff can close routes |

### TravelMethod (`SharedMemoryModel`)

Staff-authored catalog of travel methods with speeds.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField(100, unique) | "On Foot", "Sailing Ship" |
| `travel_mode` | CharField(TravelMode) | LAND, SEA, or AIR |
| `base_speed` | FloatField | Distance units per IC hour |
| `ship_type` | FK(ShipType, null) | If set, speed overridden by effective_handling() |
| `is_default` | BooleanField | The default method (On Foot) |

### Voyage (`SharedMemoryModel`)

Tracks a group's progress through a multi-leg route.

| Field | Type | Description |
|-------|------|-------------|
| `leader` | FK(Persona) | The character leading the voyage |
| `travel_method` | FK(TravelMethod) | How the group is traveling |
| `origin_hub` | FK(TravelHub, null) | Where the voyage started |
| `destination_hub` | FK(TravelHub, null) | Where the voyage is going |
| `route_hubs` | JSONField(list) | Ordered list of hub PKs |
| `current_leg_index` | PositiveSmallIntegerField | Index into route_hubs |
| `status` | CharField(VoyageStatus) | IN_TRANSIT, ARRIVED, ABANDONED |
| `ship` | OneToOneField(ShipDetails, null) | Ship being sailed (optional) |
| `started_at` | DateTimeField(auto_now_add) | When voyage began |
| `completed_at` | DateTimeField(null) | When voyage ended |

### VoyageParticipant (`SharedMemoryModel`)

M2M through model linking characters to a Voyage.

| Field | Type | Description |
|-------|------|-------------|
| `voyage` | FK(Voyage) | The voyage |
| `persona` | FK(Persona) | The traveling character |
| `joined_at` | DateTimeField(auto_now_add) | When they joined |
| `left_at` | DateTimeField(null) | If they left mid-voyage |
| `legs_traveled` | PositiveSmallIntegerField | How many legs paid for |

## Service Functions (`services.py`)

### Pathfinder

```python
from world.travel.services import find_overworld_route

route = find_overworld_route(origin_hub, destination_hub, travel_mode)
# -> list[TravelRoute] (ordered edges) | None
```

BFS over TravelRoute edges filtered by travel_mode. Returns ordered list of route edges, or None if unreachable within `OVERWORLD_MAX_HOPS`.

### Travel Time & AP Cost

```python
from world.travel.services import compute_travel_time, compute_ap_cost

time = compute_travel_time(route, travel_method, character_sheet, ship=None)
# -> float (IC hours)

ap = compute_ap_cost(time)
# -> int (ceil(time * AP_PER_IC_HOUR), min 1)
```

**Formula:**
- `effective_speed = method.base_speed * ship_handling_factor * (1 + speed_modifier / 100)`
- `time = route.distance / effective_speed * route.difficulty_modifier`
- `ap_cost = ceil(time * AP_PER_IC_HOUR)`

### Voyage Lifecycle

```python
from world.travel.services import start_voyage, advance_leg, complete_voyage, abandon_voyage

voyage = start_voyage(leader=persona, destination_hub=hub, travel_method=method)
advance_leg(voyage, caller=persona)      # Pay AP, move to next hub (tempus fugit)
complete_voyage(voyage, caller=persona)   # Pay all remaining AP, fast-forward to destination
abandon_voyage(voyage, caller=persona)    # End voyage at current hub
```

- **Leader authority:** Only the leader can advance/complete. Any participant can abandon (non-leader only removes themselves).
- **Partial failure:** Participants who can't afford AP are left at the current hub. If the caller can't afford AP, the advance fails atomically.
- **Auto-complete:** When `advance_leg` reaches the final hub, voyage status → ARRIVED.
- **Concurrency:** `select_for_update()` on the Voyage row prevents double-advancement races.

## Actions (`actions/definitions/voyages.py`)

Four REGISTRY actions, all `category="movement"`:

| Action | Key | Target | Description |
|--------|-----|--------|-------------|
| `StartVoyageAction` | `start_voyage` | SINGLE | Set destination, compute route, create Voyage |
| `AdvanceLegAction` | `advance_voyage_leg` | SELF | Pay AP for next leg, move group to next hub |
| `CompleteVoyageAction` | `complete_voyage` | SELF | Pay remaining AP, fast-forward to destination |
| `AbandonVoyageAction` | `abandon_voyage` | SELF | End voyage at current hub |

## Telnet Command (`commands/voyages.py`)

`CmdVoyage` (`voyage`):
- `voyage <destination>` — start a voyage to a named hub
- `voyage method <method>` — set travel method
- `voyage advance` — advance to next hub (tempus fugit)
- `voyage arrive` — complete voyage (fast-forward)
- `voyage stop` — abandon voyage
- `voyage status` — show current voyage progress

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `AP_PER_IC_HOUR` | 2 | AP cost per IC hour of travel |
| `OVERWORLD_MAX_HOPS` | 20 | Max hubs in a computed route |

## Integration Points

- **Action Points**: Each participant spends their own AP via `ActionPointPool.spend()`.
- **Ship System**: Ships map to TravelMethod via `ShipType`. Ship handling upgrades reduce travel time.
- **Scene System**: Zero changes — hubs are real rooms, scenes work as-is.
- **Game Clock**: `get_ic_now()` used for voyage timestamps. Travel time is in IC hours.
- **Mechanics**: `travel` ModifierCategory + `travel_speed` ModifierTarget for speed modifiers (plumbing only — no source populates it yet).
- **RoomProfile**: Not modified — TravelHub OneToOne is the sole source of truth for hub status.

## Embarkation Constraint

Voyages can only be started or ended at a TravelHub whose `travel_modes` include the voyage's travel method mode. A pier serves SEA voyages; a city gate serves LAND voyages. The `is_transit_stop` flag controls whether a hub appears as an intermediate waypoint in route BFS (`True`) or is an embarkation/disembarkation point only (`False`).
