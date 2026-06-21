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
  as the sole encounter read-gate: staff bypass OR `scene__in=Scene.objects.viewable_by(user)`.
  The participant union is gone — every encounter carries a required scene, so scene
  visibility subsumes participant membership (`src/world/combat/views.py`).
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

```python
from world.scenes.place_services import ensure_scene_for_location

# Find or create the active scene for a room.  If an active scene already
# exists the caller's privacy_mode is ignored and the existing scene is
# returned unchanged.  When a new scene is created, privacy_mode is derived
# from the room when omitted — PUBLIC if the room is publicly listed, else
# PRIVATE.  Used by combat encounter-start to guarantee every encounter
# carries a scene.
scene = ensure_scene_for_location(room, privacy_mode=ScenePrivacyMode.PRIVATE)
```

### Scene Privacy ↔ Room-Publicness Invariant (#1287)

**The rule (one-directional):** a `Scene` whose `location` is a publicly-listed
room **must** have `privacy_mode == PUBLIC`. Hosting a PRIVATE or EPHEMERAL scene
in a space anyone can enter would allow RP-leak. The constraint is one-directional:
scenes in non-public rooms, scenes with no location, and scenes in rooms that lack
a `RoomProfile` are completely unconstrained.

**Publicness test:** a room is "publicly listed" when
`room.room_profile.is_public` is `True`. A missing `RoomProfile` is treated as
not-public (fail-closed), so unconfigured rooms impose no constraint.

**EPHEMERAL is stricter than PRIVATE.** Both PRIVATE and EPHEMERAL are forbidden
in publicly-listed rooms; the rule blocks anything that is not PUBLIC.

**Two enforcement points:**

1. `ensure_scene_for_location(room)` (`place_services.py`) — when `privacy_mode`
   is omitted, the default is derived from the room: `PUBLIC` if
   `room_is_publicly_listed(room)`, else `PRIVATE`. This is the creation
   chokepoint; callers that pass an explicit mode get no derivation, but the
   `Scene.save()` guard (below) will still fire if the mode violates the invariant.

2. `Scene._validate_privacy_against_room()` wired into both `Scene.save()` and
   `Scene.clean()` — raises `ValidationError({"privacy_mode": "..."})` when a
   non-PUBLIC scene has a publicly-listed-room `location`. Every ORM `save()`
   call, including serializer `.save()`, hits this guard.

**Shared helper:**

```python
from evennia_extensions.models import room_is_publicly_listed

room_is_publicly_listed(room) -> bool
# Returns room.room_profile.is_public, or False when the RoomProfile is absent.
# Single source of truth consumed by Scene validation and ensure_scene_for_location.
```

**Sceneless-interaction reconciliation:** the invariant governs scenes that
*exist*. Combat no longer creates null-scene encounters (every encounter now
carries a required scene). However, non-scene interactions legitimately remain
sceneless — the `scene__isnull=True` branch in `Interaction.objects.visible_to`
(`world/scenes/managers.py`) treats them as public-visible and this is intentional,
unchanged behaviour.

**Events obey the invariant:** The rule is enforced at config time (create/edit)
and at start time. `Event.is_public` is *calendar visibility* (a different axis
from `RoomProfile.is_public`, which governs room listing).

*Config time:* `Event.clean()` (wired into the admin ModelForm) and
`_EventScheduleMixin.validate()` (shared by `EventCreateSerializer` and
`EventUpdateSerializer`) both reject a private event (`is_public=False`) whose
`location.is_public` is `True`. This means a GM cannot save or submit a private
event for a publicly-listed room — they hit the error at create or edit, not at
start.

*Start time:* `start_event` (`world/events/services.py`) enforces the rule again
as the events chokepoint. When `start_event` derives `privacy_mode` as PRIVATE
(i.e. the event is not public on the calendar), it checks `event.location.is_public`;
if the room is publicly listed, it raises `EventError.PRIVATE_IN_PUBLIC_ROOM` before
the `Scene` is created. The `Scene.save()` guard remains the final backstop for any
path that bypasses both chokepoints.

**Out of scope:**

- No retroactive re-derivation: if a room's `is_public` flag flips *after* a scene
  has been created, existing scenes are not automatically updated. The guard fires
  only at `save()` / `clean()` time on the `Scene` instance itself.
- `bulk_create` bypasses `save()` and therefore bypasses the guard. Do not use
  `Scene.objects.bulk_create` to create scenes without manually enforcing the
  invariant.

```python
from world.scenes.interaction_services import ensure_scene_participation

# Create a SceneParticipation for the character's account in the scene if one
# does not already exist.  Public API — callable by any system that must record
# a character as a first-class scene participant.  Combat calls this from
# _create_participant so every fighter is a recorded scene participant.
ensure_scene_participation(scene, character)
```

---

## Scene Action Requests

Social actions within a scene require OOC consent. The `SceneActionRequest` model
owns the full lifecycle (dispatch → consent → resolution → result recording) for
**primary-target** requests; `SceneActionTarget` rows extend the same request to
**additional targets**, each with its own independent consent and result.

**Source:** `src/world/scenes/action_models.py`, `action_services.py`,
`action_views.py`, `action_serializers.py`, `action_filters.py`

### Effort / Difficulty split

- **Initiator declares effort** at dispatch via `effort_level` (`EffortLevel` TextChoices,
  default `"medium"`). This is forwarded from `create_action_request` → stored on
  `SceneActionRequest.effort_level`. At resolution `_resolve_action_against_persona`
  reads `EFFORT_CHECK_MODIFIER[effort_level]` and adds it to the check pool, then
  charges the initiator social fatigue via `apply_fatigue`. This applies on **both**
  the plain and the technique-enhanced (`_resolve_enhanced_action` → `use_technique`)
  branches (#1293): effort is a check-roll modifier, orthogonal to the technique's
  anima/intensity/fury levers (which scale cast power).
- **Defender authors difficulty** via a plausibility band (`DifficultyChoice`) at consent
  time — not the initiator. The defender's choice is stored as `difficulty_choice` on
  the per-target row (`DefenderConsentFields.difficulty_choice`, default `NORMAL`).
  Three frontend labels map to bands: "It works" → `EASY`, "Hard but possible" → `HARD`,
  "No way" → `DAUNTING` (accept-but-daunting, distinct from deny).
- **Active resistance (optional).** When the defender selects "Dig in (costs stamina)",
  `resist_effort_level` (`EffortLevel`) is also stored at consent. On resolution,
  `compute_resist_increment(defender, resist_effort)` in `world.checks.services` resolves
  the `Composure` CheckType (willpower-weighted) and combines it with the effort modifier.
  The increment is added to the base `DIFFICULTY_VALUES[difficulty_choice]` to form
  `difficulty_override`, and the defender is charged `RESIST_FATIGUE_BASE` units of social
  fatigue.
- **NPC/area fallback.** When there is no consenting player, `difficulty_choice` defaults
  to its authored value (never an initiator pick); area actions use their own field.

### Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DefenderConsentFields` | Abstract base — per-defender consent fields shared by primary and additional targets | `difficulty_choice` (DifficultyChoice), `resolved_difficulty`, `resist_effort_level` (EffortLevel), `engagement_credited` |
| `SceneActionRequest` | Primary targeted (or area) social action request | `scene`, `initiator_persona`, `target_persona` (nullable), `action_key`, `action_template`, `technique`, `status` (ActionRequestStatus), `effort_level` (EffortLevel), `delivery`, `pose_text`, `created_at`, `resolved_at` — plus all `DefenderConsentFields` columns |
| `SceneActionTarget` | One additional non-primary target in a multi-target request | `action_request` (FK → SceneActionRequest), `target_persona`, `status`, `result_interaction`, `resolved_at` — plus all `DefenderConsentFields` columns |
| `SceneCastPullDeclaration` | Paid thread-pull declared alongside a benign standalone cast | `request` (OneToOne), `resonance`, `tier`, `threads` (M2M) |

`SceneActionTarget` has a `UniqueConstraint` on `(action_request, target_persona)` —
a persona cannot appear as an additional target more than once per request.

### Per-Target Resolver Semantics (#1178)

When an action has a registered resolver (`action_resolvers.get_resolver(action_key)`),
it fires **once per accepted target**:

- `respond_to_action_request(action_request, decision)` — fires the resolver for the
  primary target when the decision is ACCEPT (line ~340 in `action_services.py`).
- `respond_to_action_target(action_target, decision)` — fires the same resolver for
  each accepted additional target row, independently of the primary and of sibling rows.

**Idempotency contract:** a resolver registered for a multi-target action is invoked
once per accepted `SceneActionTarget`; any cast-level side-effects (e.g. anima deduction,
kudos, renown) must therefore be idempotent with respect to invocation count across targets.
NPC targets are auto-accepted at dispatch time via `_auto_resolve_npc_targets()`.

### Key Service Functions

```python
from world.scenes.action_services import (
    create_action_request,
    respond_to_action_request,
    respond_to_action_target,
)

# Create a request (primary + additional targets).
# NPC additional targets are auto-resolved immediately.
# effort_level is the initiator's declared EffortLevel value (default "medium").
request = create_action_request(
    scene=scene,
    initiator_persona=persona,
    target_persona=primary_target,      # None for area actions
    action_key="intimidate",
    additional_target_personas=[p2, p3],
    effort_level="high",                # optional; controls check modifier + initiator fatigue
)

# Primary-target consent.
# difficulty: DifficultyChoice value authored by the defender (plausibility band).
# resist_effort: optional EffortLevel for active resistance (costs defender fatigue).
result = respond_to_action_request(
    action_request=request,
    decision=ConsentDecision.ACCEPT,
    difficulty="hard",            # defender's plausibility band
    resist_effort="high",         # optional active resistance
)

# Additional-target consent — same signature, never touches siblings or the primary status.
result = respond_to_action_target(
    action_target=target_row,
    decision=ConsentDecision.ACCEPT,
    difficulty="normal",
    resist_effort="",
)
```

`ConsentResponseSerializer` accepts `difficulty` (DifficultyChoice choice string) and
`resist_effort` (EffortLevel choice string) in the POST body of
`POST /api/action-requests/{id}/respond/`.

`_resolve_action_against_persona(action_request, target, difficulty_override=None)` is
the single check-and-fatigue resolution point; `difficulty_override` is the numeric value
produced by combining the defender's plausibility base with any active-resistance increment.

### Good-Sport Kudos Accrual

When a defender accepts an action request, `_accrue_engagement_for_primary` (primary target)
and `_accrue_engagement_for_persona` (additional targets) record a social-engagement credit.
The credit amount is `KudosDifficultyWeight.weight_for(band) × KudosSourceCategory.default_amount`
and is added to the defender's `WeeklySocialEngagement` pending ledger via
`progression.services.engagement.accrue()`. Anti-farm guards: NPC defenders/initiators and
self-targeting are skipped. At weekly rollover (`grant_social_engagement_kudos()`), ledgers
with `distinct_initiators >= MIN_ENGAGEMENT_BAR` (currently 2) are granted Kudos and marked.

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

### Action Requests (`/api/action-requests/`)
- `GET /api/action-requests/` - List requests where the caller is initiator or primary target
- `POST /api/action-requests/` - Dispatch a new action request (single- or multi-target)
- `POST /api/action-requests/{id}/respond/` - Accept or deny a primary-target request; also handles additional-target consent when `target_persona_id` is included in the payload

**Filters:** `scene`, `status`, `initiator`, `target`

### Action Targets (`/api/action-targets/`)

Read-only listing of a player's pending additional-target consent rows (#1177).

- `GET /api/action-targets/` - List `SceneActionTarget` rows where the caller controls the target persona

**Filters:** `scene`, `status`

**Typical use:** `GET /api/action-targets/?scene={id}&status=pending` — fetched by `ConsentPrompt` every 5 seconds to surface the additional-target consent queue alongside the primary-request queue. Accepting or denying dispatches to `POST /api/action-requests/{id}/respond/` with `target_persona_id` set.

**Response shape** (`SceneActionTargetSerializer`): `action_target_id`, `action_request_id`, `target_persona_id`, `status`, `initiator_persona`, `initiator_name`, `scene`, `action_key`, `action_template`, `technique`, `technique_name`, `pose_text`, `strain_commitment`, `created_at`, `combat_risk_level`.

`combat_risk_level` is computed from the row's own target persona — mirroring the primary-request field — so additional targets of a hostile AOE cast receive the same combat-risk warning in `ConsentPrompt` as the primary target does (#1259).

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
