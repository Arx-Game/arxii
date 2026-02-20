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
| `InstancedRoom` | Lifecycle tracker for a temporary room | `room` (OneToOne to ObjectDB), `owner` (FK to `character_sheets.CharacterSheet`, nullable), `return_location` (FK to ObjectDB, nullable), `source_key` (placeholder for future mission FK), `status` (InstanceStatus), `created_at`, `completed_at` |

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
)
# Creates: Evennia Room object, ObjectDisplayData, InstancedRoom record

# Complete an instance: mark done, relocate occupants, optionally delete
complete_instanced_room(room)
# 1. Sets status=COMPLETED with timestamp (atomic)
# 2. Moves puppeted characters to return_location (or owner's home)
# 3. Deletes room if no meaningful data (no scenes recorded)
```

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

1. **Spawn**: `spawn_instanced_room()` creates an Evennia room, sets its display description, and creates the `InstancedRoom` tracking record
2. **Active**: Room is in use; characters can enter and interact
3. **Complete**: `complete_instanced_room()` marks it done, relocates occupants to `return_location` (falling back to owner's home), and deletes the room if no scenes were recorded

---

## Integration Points

- **Scenes**: Rooms with recorded scenes are preserved after completion
- **Character Sheets**: `owner` FK tracks which character owns the instance
- **Evennia**: Rooms are created via `evennia.utils.create.create_object` with the `Room` typeclass
- **Display Data**: `ObjectDisplayData` is used for room description (from `evennia_extensions`)

---

## Admin

- `InstancedRoomAdmin` - List with room, owner, status, source_key, created_at; filterable by status; searchable by room name and source_key
