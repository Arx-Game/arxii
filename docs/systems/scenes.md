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
| `DefenderConsentFields` | Abstract base — per-defender consent fields shared by primary and additional targets | `difficulty_choice` (DifficultyChoice), `resolved_difficulty`, `resist_effort_level` (EffortLevel) |
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

## Scene Administration (#1445)

**Source:** `src/world/scenes/scene_admin_services.py`, `src/actions/definitions/scenes.py`,
`src/actions/definitions/rounds.py`, `src/commands/scene.py`

### Co-ownership model

All characters **present in the room at scene creation** become co-owners (`is_owner=True` on
their `SceneParticipation`). Latecomers who join after the scene has started are non-owner
participants — they cannot inadvertently acquire admin rights by entering a room mid-scene
(anti-grab rule). A GM or staff character bypasses the ownership check entirely; they can
administer any scene regardless of participation.

### Permission helper

```python
from world.scenes.scene_admin_services import actor_can_administer_scene

# True if actor may administer the scene (finish it, change round mode, etc.)
actor_can_administer_scene(actor, scene) -> bool
```

Authorization tiers (first match wins):

1. `actor.is_story_runner` — `GMCharacter` and `StaffCharacter` set this to `True`
   (`src/typeclasses/gm_characters.py`); no account lookup is performed.
2. The actor's controlling account is a staff user (`account.is_staff`).
3. The actor's controlling account has `is_owner=True` on a `SceneParticipation` row for
   this scene.

```python
from world.scenes.scene_admin_services import resolve_actor_account

# Return the controlling AccountDB for actor (PC tenure path), or None for GM/Staff/NPC.
resolve_actor_account(actor) -> AccountDB | None
```

### Service functions

```python
from world.scenes.scene_admin_services import add_present_as_co_owners

# Mark every present character with a controlling account as a scene co-owner.
# Walks room.contents; skips NPCs, props, and characters without a controlling account.
# Called by StartSceneAction immediately after scene creation.
add_present_as_co_owners(scene, room) -> None
```

```python
from world.scenes.scene_admin_services import finish_scene_full

# Full scene-finish orchestration. Idempotent — returns immediately if already finished.
# Steps: scene.finish_scene() → on_scene_finished() → deferred fatigue resets →
#        broadcast_scene_message(scene, SceneAction.END).
# by_account is accepted for call-site symmetry but is not forwarded downstream.
finish_scene_full(scene, by_account=None) -> None
```

```python
from world.scenes.round_services import maybe_finish_empty_scene

# Auto-close (#1361): finishes room's active scene via finish_scene_full if no
# PC other than `leaving` remains in room.contents. No-ops if no active scene.
# Skips a scene with a live CombatEncounter/Battle attached (that scene's
# lifecycle belongs to the encounter/battle outcome, not room emptiness — and
# such scenes lack the account/participant data finish_scene_full needs).
# Called from Room.at_object_leave (movement) and Character.at_post_unpuppet
# (disconnect, after Evennia's own base-class relocation has already run).
maybe_finish_empty_scene(room, *, leaving=None) -> None
```

### Lifecycle Actions

**`StartSceneAction`** (`key="start_scene"`, `src/actions/definitions/scenes.py`)

Creates a scene in the actor's current room via `ensure_scene_for_location`, then calls
`add_present_as_co_owners` so every present PC is a co-owner. If an active scene already
exists, the actor is recorded as a non-owner participant. Ungated — any character may invoke it.

**`FinishSceneAction`** (`key="finish_scene"`, `src/actions/definitions/scenes.py`)

Finishes the active scene in the actor's room. Gated by `actor_can_administer_scene` — only
a GM character, staff account, or scene co-owner succeeds. Delegates to `finish_scene_full`
for full orchestration.

### Round-mode service — active_round_for_room

```python
from world.scenes.round_services import active_round_for_room

# Return the active (non-completed) SceneRound for a room, or None.
# Relies on the one-active-scene-round-per-room DB constraint, so .first() is
# unambiguous.  Public service — promoted from the private _active_round_for_room
# helper that was previously inlined in SetRoundModeAction (#1467).
active_round_for_room(room) -> SceneRound | None
```

### Round-mode control

```python
from world.scenes.round_services import set_scene_round_mode, RoundModeError

# Apply mode and/or knob changes to scene_round in-place.
# Guard (raises RoundModeError):
#   - Leaving STRICT while pending non-immediate declarations exist is blocked;
#     caller must force-resolve first. (#1466 removed the DANGER-specific block —
#     a danger round is an ordinary STRICT round whose mode/knobs are settable.)
# Only supplied (non-None) fields are written (update_fields pattern).
set_scene_round_mode(
    scene_round,
    *,
    mode=None,                   # SceneRoundMode value (OPEN/POSE_ORDER/STRICT)
    advance_quorum_pct=None,     # int — quorum % to advance the pose-order round
    max_actions_per_round=None,  # int — per-participant action cap per round
    per_target_repeat_lock=None, # bool — block repeat targeting of the same persona
) -> SceneRound
```

**`SetRoundModeAction`** (`key="set_round_mode"`, `src/actions/definitions/rounds.py`)

Changes the mode and/or knobs of the active scene round. Guard order in `execute()`:

1. Actor must be in a room.
2. The room must have an active scene (requires scene context — start one first).
3. The actor must be a scene admin per `actor_can_administer_scene`.
4. The room must have an active round to modify.
5. `set_scene_round_mode` validates the mode transition (STRICT-exit blocked by pending deferred
   declarations).

`costs_turn = False` — mode changes do not consume a round action.

**`StartRoundAction`** (`key="start_round"`, `src/actions/definitions/rounds.py`) — extended
in this feature: if any knob override (`mode`, `advance_quorum_pct`, `max_actions_per_round`,
`per_target_repeat_lock`) is supplied, the actor must be a scene admin before the round is
created with those overrides applied at creation time.

### Telnet command — `CmdScene`

**Source:** `src/commands/scene.py`

```
scene                                     — show active scene + round status
scene status                              — same
scene start [name]                        — StartSceneAction (name optional)
scene finish                              — FinishSceneAction
scene round [open|pose_order|strict]      — SetRoundModeAction; any knobs optional
         [quorum=<pct>] [cap=<n>] [lock=on/off]
```

Example: `scene round strict quorum=70 cap=2 lock=on`

No business logic lives in `CmdScene` — all routing is delegated to the three Actions above.
Mode tokens (`open` / `pose_order` / `strict`) are mapped to `SceneRoundMode` values by
`_parse_round_args`. Lock values: `on` / `true` / `yes` / `1` → True; anything else → False.

### Web endpoint

`POST /api/scenes/{id}/set-round-mode/` — coarse-gated by `IsSceneGMOrOwnerOrStaff`; the
authoritative permission check runs inside `SetRoundModeAction`. The viewset resolves the
requesting account's active character as the action actor so that telnet and web converge on
the same `action.run()` seam. Returns the updated scene detail on success.

### Web round-mode control — RoundSettingsDialog (#1467)

`RoundSettingsDialog` (`frontend/src/scenes/components/RoundSettingsDialog.tsx`) is the
React-side parity for `scene round` (telnet, #1445).

**Gate:** rendered only when `scene.viewer_can_gm && scene.is_active`; matches the backend
`IsSceneGMOrOwnerOrStaff` coarse gate on `POST /api/scenes/{id}/set-round-mode/`.

**Behaviour:**
- When `scene.active_round` is `null` (no active round), the dialog body shows an
  informational message; Save is disabled.
- When a round exists, the dialog exposes mode (Select), advance quorum % (Input),
  max actions per round (Input), and repeat-target lock (Switch). All controls are
  editable for every round, including danger rounds — since #1466 a danger round is an
  ordinary STRICT round and `set_scene_round_mode` accepts knob/mode changes for it like
  any other round (web/telnet parity, #1328, #1476). When `active_round.is_danger` is
  true the dialog shows a non-blocking informational note explaining the round was started
  by an unfolding peril and auto-ends when it clears; it does **not** lock anything.
- On Save, dispatches `useSetRoundMode` → `POST /api/scenes/{id}/set-round-mode/` with a
  `SetRoundModePayload`; closes the dialog on success.

**Wire-point:** `RoundSettingsDialog` is rendered by `SceneHeader.tsx` alongside the
Edit and End Scene buttons.

**Read-side serialization:** `SceneDetailSerializer` exposes `active_round` as a nullable
nested field serialized by `SceneRoundSerializer` (read-only). Fields:

| Field | Type | Notes |
|-------|------|-------|
| `mode` | string | `SceneRoundMode` value (`open` / `pose_order` / `strict`) |
| `advance_quorum_pct` | int | % of distinct actors needed to advance a POSE_ORDER round |
| `max_actions_per_round` | int | Per-participant action cap per round |
| `per_target_repeat_lock` | bool | Block repeat targeting of the same persona |
| `status` | string | `RoundStatus` value |
| `round_number` | int | Current round counter |
| `is_danger` | bool | Derived: `True` when `start_reason == DANGER` |

`active_round` is `null` when the scene has no location or no active round exists.

The `is_danger` field remains a read-side hint: the dialog uses it only to show the
informational note above, never to disable controls (#1476 cleared the old danger lock).

---

## Permissions

| Permission Class | Used For | Rule |
|-----------------|----------|------|
| `IsSceneOwnerOrStaff` | Scene edit/delete | Owner participation or staff |
| `IsSceneGMOrOwnerOrStaff` | Scene finish + set-round-mode | GM or owner participation, or staff |
| `IsMessageSenderOrStaff` | Message edit/delete | Persona's account matches user AND scene is active |
| `CanCreatePersonaInScene` | Persona creation | User must own the participation referenced |
| `CanCreateMessageInScene` | Message creation | User must own the persona AND be a scene participant |
| `ReadOnlyOrSceneParticipant` | Scene retrieve | Delegates read check to `scene.is_viewable_by(request.user)` (the canonical predicate) |

---

## Admin

- `SceneAdmin` - List display with participant count; inline participations and messages
- `PersonaAdmin` - Search by name, scene name, account username
- `SceneMessageAdmin` - Inline supplemental data and reactions; filterable by context, mode, active status
