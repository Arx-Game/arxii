# Instances System

Temporary instanced rooms spawned on demand for missions, GM events, and personal scenes.

**Source:** `src/world/instances/`

---

## Enums (constants.py)

```python
from world.instances.constants import InstanceStatus
# Values: ACTIVE, COMPLETED
```

---

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `InstancedRoom` | Lifecycle tracker for a temporary room | `room` (OneToOne to `evennia_extensions.RoomProfile`, #2608), `owner` (FK to `character_sheets.CharacterSheet`, nullable, `related_name="owned_instances"`), `gm_owner` (FK to `gm.GMProfile`, nullable — the GM who spun this instance up, e.g. story scene rooms, #2450; also `related_name="owned_instances"`, on a different model, so both FKs' reverse accessors coexist without collision), `return_location` (FK to ObjectDB, nullable — a **deliberate keeper**: the captivity path stamps a raw, unvalidated `character.location` with no Room guarantee), `source_key` (placeholder for future mission FK), `entrance_exit` (FK to `evennia_extensions.ExitProfile`, nullable, `SET_NULL`; the temporary one-way doorway from the anchor room into this instance, #696 gap 7), `status` (InstanceStatus), `created_at`, `completed_at` |

`owner` and `gm_owner` are independent nullable FKs, not a mutually-exclusive pair
enforced anywhere — a player-owned instance and a GM-spun instance both use the
same lifecycle machinery, and either, both, or neither may be set on a given row.

---

## Key Methods

### Service Functions

```python
from world.instances.services import spawn_instanced_room, complete_instanced_room

# Create a temporary instanced room
room = spawn_instanced_room(
    name="Dark Cavern",
    description="A damp cave with strange markings...",
    owner=character_sheet,
    return_location=town_square_room,
    source_key="mission_goblin_cave",
    anchor_room=town_square_room,   # optional: mints a one-way entrance from here
    area=None,                      # optional: authored override for the room's Area
)
# Creates: Evennia Room object, ObjectDisplayData, InstancedRoom record, and with an
# anchor_room a one-way entrance exit (anchor -> instance) carrying the
# `instance_entrance` behavior package, recorded on InstancedRoom.entrance_exit

# Complete an instance: mark done, relocate occupants, optionally delete
complete_instanced_room(room)
# 1. Sets status=COMPLETED with timestamp (atomic)
# 2. Moves puppeted characters to return_location (or owner's home)
# 3. Deletes the entrance exit, if one was minted
# 4. Deletes room if no meaningful data (no scenes recorded)
```

### Entrances and area inheritance (#696 gap 7)

The spawned profile's `area` is the explicit `area` when given (an authored override,
or the task-target domain's Area a caller resolved), else `anchor_room`'s area, else
None. With an `anchor_room`, `spawn_instanced_room` mints a one-way exit from it into
the instance (`areas.grid_services.create_exit`, the #3860 one-way helper; leaving
happens through `complete_instanced_room`'s relocation, never a return exit) and
attaches the `instance_entrance` behavior package
(`behaviors/instance_entrance_package.py`) on `can_traverse`: only the instance's
owning character, a participant of the mission run that spawned it, and the GM owner
(matched by account) may use it. The room-state serializer
(`flows/service_functions/serializers/room_state.py`, `_exit_hidden_from_looker`)
hides the entrance from any looker the package would refuse, so bystanders in the
anchor room never see a doorway they could not use; there is no story-runner bypass
for this gate. Mission resolution passes `anchor_room=<the runner's location>` and
`area=option.instance_area or <the fulfilled OrgTask's target-domain area>`
(`missions/services/resolution.py`, `_task_target_area`); GM story and captivity
callers pass no anchor.

### Validation

```python
# InstancedRoom.clean() validates return_location is a Room typeclass
instance.clean()  # Raises ValidationError if return_location is not a Room
```

### Data Preservation

```python
from world.instances.services import _has_meaningful_data

# Room is kept if it has associated Scene records, deleted otherwise
_has_meaningful_data(room)  # True if Scene.objects.filter(location=room).exists()
```

---

## Lifecycle

1. **Spawn**: `spawn_instanced_room()` creates an Evennia room, sets its display description, resolves its Area (explicit, else the anchor's), mints the package-gated entrance when anchored, and creates the `InstancedRoom` tracking record
2. **Active**: Room is in use; the run's people enter through the entrance, everyone else neither sees nor passes it
3. **Complete**: `complete_instanced_room()` marks it done, relocates occupants to `return_location` (falling back to owner's home), deletes the entrance exit, and deletes the room if no scenes were recorded

---

## Integration Points

- **Scenes**: Rooms with recorded scenes are preserved after completion
- **Character Sheets**: `owner` FK tracks which character owns the instance
- **Evennia**: Rooms are created via `evennia.utils.create.create_object` with the `Room` typeclass
- **Display Data**: `ObjectDisplayData` is used for room description (from `evennia_extensions`)
- **Areas**: `RoomProfile.area` is inherited from the anchor room or set from an authored override; `grid_services.create_exit` mints the one-way entrance
- **Behaviors**: the `instance_entrance` package (`can_traverse` hook `restrict_to_run`) gates the entrance; `entrance_refuses()` is its serializer-side twin
- **Missions**: `MissionOption.instance_area` is the authored Area override; resolution anchors the spawn at the runner's location and inherits a fulfilled `OrgTask`'s target-domain Area

---

## Admin

- `InstancedRoomAdmin` - List with room, owner, status, source_key, created_at; filterable by status; searchable by room name and source_key
