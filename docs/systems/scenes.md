# Scenes System

Roleplay session recording with persona-based identity, message logging, and real-time broadcasting.

**Source:** `src/world/scenes/`
**API Base:** `/api/scenes/`, `/api/personas/`, `/api/messages/`, `/api/reactions/`

---

## Enums (constants.py)

```python
from world.scenes.constants import (
    MessageContext,  # PUBLIC, TABLETALK, PRIVATE
    MessageMode,     # POSE, EMIT, SAY, WHISPER, OOC
)
```

---

## Models

### Scene Recording (SharedMemoryModel + models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Scene` | Primary scene entity (SharedMemoryModel, cached) | `name`, `description`, `location` (FK ObjectDB), `date_started`, `date_finished`, `is_active`, `is_public` |
| `SceneParticipation` | Links accounts to scenes with roles | `scene` (FK), `account` (FK AccountDB), `is_gm`, `is_owner`, `joined_at`, `left_at` |
| `Persona` | Identity a participant uses within a scene | `participation` (FK), `name`, `is_fake_name`, `description`, `thumbnail_url`, `character` (FK ObjectDB) |

### Messages

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SceneMessage` | A message sent during a scene | `scene` (FK), `persona` (FK), `content`, `context` (TextChoices), `mode` (TextChoices), `receivers` (M2M Persona), `timestamp`, `sequence_number` |
| `SceneMessageSupplementalData` | Extra metadata for messages (1:1) | `message` (OneToOne, primary_key), `data` (JSONField) |
| `SceneMessageReaction` | Emoji reaction to a message | `message` (FK), `account` (FK AccountDB), `emoji` |

---

## Key Methods

### Scene

```python
from world.scenes.models import Scene

# Check if scene is finished
scene.is_finished  # property: date_finished is not None

# Check ownership
scene.is_owner(account)  # True if account has is_owner participation

# Finish a scene (sets date_finished, is_active=False)
scene.finish_scene()

# Cached participations (avoids repeated queries)
scene.participations_cached  # list of SceneParticipation with select_related("account")
```

### Read-Visibility Surface (canonical)

These are the **single source of truth** for scene read-access. All read gates in the
codebase consume one of these two forms — never inline the logic elsewhere.

```python
from world.scenes.models import Scene

# Queryset form — use in get_queryset() / filter() chains
Scene.objects.viewable_by(account)
# staff        → all scenes
# authenticated non-staff → public OR participant
# anonymous / None → public only

# Predicate form — use for per-instance object-permission checks
scene.is_viewable_by(account)
# Same semantics; reads participations_cached (zero queries when the scene
# is already in the identity map — same approach as is_gm / is_owner).
```

**Interaction** read-access has its own canonical queryset surface (the pose-level tiers:
room-heard public, pinned party, present/participated scenes, GM-of-scene; very-private
excluded except for the party themselves):

```python
from world.scenes.models import Interaction

# Single source of truth for interaction read-visibility (was inlined in
# InteractionViewSet.get_queryset). Preserves any prefetches on the chain. Callers pass
# the account's CURRENT persona ids (empty for anonymous) and an optional `since` bound.
Interaction.objects.visible_to(account, persona_ids=persona_ids, since=since)
```

**Consumers:**
- `SceneViewSet.get_queryset()` calls `Scene.objects.viewable_by(request.user)` for the
  `list` action (`src/world/scenes/views.py`); retrieve is gated separately via the
  object-permission path below.
- `ReadOnlyOrSceneParticipant.has_object_permission()` calls `scene.is_viewable_by()`
  to gate read access on the scene detail / retrieve (`src/world/scenes/permissions.py`).
- `CombatEncounterViewSet._filter_readable()` calls `Scene.objects.viewable_by(user)`
  as the base of the encounter read-gate, unioned with encounter-participant membership
  (`src/world/combat/views.py`).
- `InteractionViewSet.get_queryset()` calls `Interaction.objects.visible_to(...)`
  (`src/world/scenes/interaction_views.py`).
- `SceneViewSet.highlight_reel()` calls `Interaction.objects.visible_to(...)` so the reel
  can never surface a pose the viewer cannot see — not even as a sealed slot (#1241).

### SceneMessage

```python
from world.scenes.models import SceneMessage

# Auto-assigns sequence_number on save using MAX aggregate
message = SceneMessage(scene=scene, persona=persona, content="text")
message.save()  # sequence_number auto-set
```

### SceneMessageReaction

```python
from world.scenes.models import SceneMessageReaction

# Reactions use unique_together on (message, account, emoji)
# Toggle behavior implemented in the viewset's create method
```

### Services

```python
from world.scenes.services import broadcast_scene_message

# Broadcast scene events to all accounts in the scene's location
# Caches active_scene on the room object for performance
broadcast_scene_message(scene, "start")   # Sets location.active_scene = scene
broadcast_scene_message(scene, "update")  # Sends update payload
broadcast_scene_message(scene, "end")     # Sets location.active_scene = None
```

---

## API Endpoints

### Scenes (`/api/scenes/`)
- `GET /api/scenes/` - List scenes (public + participant's private scenes)
- `POST /api/scenes/` - Create scene (auto-creates owner participation, auto-generates unique name)
- `GET /api/scenes/{id}/` - Scene detail with messages and personas
- `PUT/PATCH /api/scenes/{id}/` - Update scene (owner/staff only)
- `DELETE /api/scenes/{id}/` - Delete scene (owner/staff only)
- `POST /api/scenes/{id}/finish/` - Finish an active scene (owner/GM/staff)
- `GET /api/scenes/spotlight/` - Active scenes + recently finished (last 7 days)
- `GET /api/scenes/{id}/highlight-reel/` - Highlight reel (#1241): one **fully sealed**
  featured moment + a ranked index, ids only. Featured = highest-reacted GM-tagged pose
  (headlines even at 0 reactions — curation primacy), else the single most-reacted pose;
  index = remaining poses with ≥1 reaction, ranked by reaction count, capped at 10. Source
  set is filtered through `Interaction.objects.visible_to`, so hidden poses never appear.
  Reveal a pose via `GET /api/interactions/{id}/`.

**Filters:** `is_active`, `is_public`, `location`, `participant`, `status` (active/completed/upcoming), `gm`, `player`

### Personas (`/api/personas/`)
- `GET /api/personas/` - List personas
- `POST /api/personas/` - Create persona in a scene (participant/staff only)

**Filters:** `scene`, `participation`, `account`, `character`

### Messages (`/api/messages/`)
- `GET /api/messages/` - List messages (cursor-paginated)
- `POST /api/messages/` - Create message (scene must be active, uses `persona_id` write field)
- `PUT/PATCH /api/messages/{id}/` - Edit message (sender/staff, scene must be active)
- `DELETE /api/messages/{id}/` - Delete message (sender/staff)

**Filters:** `scene`, `persona`, `context`, `mode`

### Reactions (`/api/reactions/`)
- `POST /api/reactions/` - Toggle reaction (creates or removes based on existing state)
- `DELETE /api/reactions/{id}/` - Remove reaction

---

## Permissions

| Permission Class | Used For | Rule |
|-----------------|----------|------|
| `IsSceneOwnerOrStaff` | Scene edit/delete | Owner participation or staff |
| `IsSceneGMOrOwnerOrStaff` | Scene finish | GM or owner participation, or staff |
| `IsMessageSenderOrStaff` | Message edit/delete | Persona's account matches user AND scene is active |
| `CanCreatePersonaInScene` | Persona creation | User must own the participation referenced |
| `CanCreateMessageInScene` | Message creation | User must own the persona AND be a scene participant |
| `ReadOnlyOrSceneParticipant` | Scene retrieve | Delegates read check to `scene.is_viewable_by(request.user)` (the canonical predicate) |

---

## Admin

- `SceneAdmin` - List display with participant count; inline participations and messages
- `PersonaAdmin` - Search by name, scene name, account username
- `SceneMessageAdmin` - Inline supplemental data and reactions; filterable by context, mode, active status
