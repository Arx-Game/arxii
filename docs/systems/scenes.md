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
| `ReactionEmoji` | Staff-editable reaction-emoji catalog (#1699); nonzero valence also fires an ambient relationship bump at the pose's author | `emoji` (unique), `valence` (`ReactionValence` +1/0/−1), `is_active`, `sort_order` |

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
NPC targets — both the primary and any additional-target rows — are auto-accepted at
dispatch time via `_auto_resolve_npc_targets()` (#2214 extended this from
additional-targets-only to always run, so a lone NPC primary target resolves too,
guarded by a resolvability check so a request with no real resolution path — no
matching `ActionTemplate`, no custom resolver, not a standalone cast — stays PENDING
instead of raising).

### Key Service Functions

```python
from world.scenes.action_services import (
    create_action_request,
    respond_to_action_request,
    respond_to_action_target,
)

# Create a request (primary + additional targets).
# NPC targets (primary or additional) are auto-resolved immediately at creation (#2214).
# The primary's result, when auto-resolved, is available via the create-endpoint response's
# "result" key (or, calling the service directly, via the transient
# request._auto_resolve_result attribute) — not via this function's return value, which
# stays a bare SceneActionRequest for backward compatibility with existing callers.
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
- `GET /api/scenes/{id}/highlight-reel/` - Highlight reel (#1241, re-ranked #2161): one
  **fully sealed** featured moment + a ranked index, ids plus `vote_count`/`reaction_count`.
  Featured = highest-ranked GM-tagged pose (headlines even at 0 votes/reactions — curation
  primacy), else the single most-ranked pose; index = remaining poses with ≥1 vote or
  reaction, ranked by all-time `WeeklyVote` count first (persists past weekly settlement —
  a pose's standing outlives the week it was posed in), reaction count as tie-break, and
  recency last, capped at 10. Source set is filtered through `Interaction.objects.visible_to`,
  so hidden poses never appear. Reveal a pose via `GET /api/interactions/{id}/`.

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

### Interaction reactions + emoji catalog (#1699)
- `POST /api/interaction-reactions/` - Toggle an emoji reaction on an Interaction. When
  the emoji is an active `ReactionEmoji` with nonzero valence, the create additionally
  dispatches `RelationshipBumpAction` at the pose's author (response carries
  `bump_applied`; a deduped bump never blocks the chip, un-reacting never reverts one)
- `GET /api/reaction-emoji/` - The active catalog (`emoji`, `valence`, `sort_order`)
  the scene footer renders; staff edit rows in admin, no deploy needed

### Action Requests (`/api/action-requests/`)
- `GET /api/action-requests/` - List requests where the caller is initiator or primary target
- `POST /api/action-requests/` - Dispatch a new action request (single- or multi-target)
- `POST /api/action-requests/{id}/respond/` - Accept or deny a primary-target request; also handles additional-target consent when `target_persona_id` is included in the payload

**Filters:** `scene`, `status`, `initiator`, `target`, `role` (#2166 — `incoming`/
`outgoing`, mirroring `world.combat.filters.DuelChallengeFilter.role` verbatim;
narrows the queryset's already-account-scoped `Q(initiator_persona_id__in=...) |
Q(target_persona_id__in=...)` — every persona across every character the
account has ever played, via `get_account_personas` — down to just the
`target_persona_id__in=...` side for `incoming`). `GET
/api/action-requests/?status=pending&role=incoming` is what
`ConsentAttentionNotifier` polls for an account-wide "pending requests
addressed to any of my played characters" view; no `scene` param needed, and
it never surfaces another account's requests.

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
#        teardown conjured obstacles/ramparts → revalidate Durance engagements →
#        clear speaker queue → expire_scene_scoped_conditions(participants) (#2514) →
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

### GM enrollment (#2113)

`SceneParticipation.is_gm` is the single predicate every GM-combat surface gates on
(`Scene.is_gm`, `_actor_may_gm_encounter` in `actions/definitions/gm_combat.py`,
`IsEncounterGMOrStaff`/`can_view_encounter_effects` in `world/combat/permissions.py`). Before
#2113 the only production writer was the crossover-event path
(`_enroll_lead_gm_on_scene`, `world/stories/services/crossover.py`, untouched by this work) — an
ordinary trust-tier GM (the #1999/#2000 GMLevel ladder) running their own table's session never
got flagged. Two writers now cover the gap:

```python
from world.scenes.scene_admin_services import enroll_present_table_gms

# Auto-flag is_gm=True for any present account that owns an ACTIVE GMTable AND has at
# least one OTHER present character whose active persona holds an active
# GMTableMembership on that same table. Bare table ownership is not enough — a GM
# merely passing through a stranger's room must not auto-become that scene's
# adjudicator. Idempotent (update_or_create); never flips is_gm back to False.
enroll_present_table_gms(scene, room) -> None
```

Called from `StartSceneAction.execute()` right after `add_present_as_co_owners` (new scene) and
again on the mid-scene join branch (existing scene), so a table-owning GM arriving after scene
start still gets flagged.

**`GrantSceneGMAction`** (`key="grant_scene_gm"`, `src/actions/definitions/scenes.py`) is the
fallback for cases auto-detection can't reach (pickup games, guest players, an Assistant GM the
scene owner wants to co-adjudicate). Gated: the actor must already administer the scene
(`actor_can_administer_scene`) and the named, present target account must hold a `GMProfile`
(any level — approval is itself the trust gate, no `GMLevel` tier check here).
`update_or_create`s the target's `SceneParticipation.is_gm=True`. Telnet: `scene gm <name>`
(`CmdScene`, `src/commands/scene.py`). Web reaches the same Action through the generic
available-actions dispatcher (mirrors `set_the_stage`); a minimal "Grant GM" control lives next
to the co-owner list in `SceneHeader.tsx`, visible only when `actor_can_administer_scene` is true
for the viewer.

### Lifecycle Actions

**`StartSceneAction`** (`key="start_scene"`, `src/actions/definitions/scenes.py`)

Creates a scene in the actor's current room via `ensure_scene_for_location`, then calls
`add_present_as_co_owners` and `enroll_present_table_gms` so every present PC is a co-owner and
any table-owning GM with a present member is auto-flagged `is_gm`. If an active scene already
exists, the actor is recorded as a non-owner participant and `enroll_present_table_gms` runs
again for the room. Ungated — any character may invoke it.

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
scene decisive <beat-id>                  — MarkDecisiveCheckAction (#1748)
scene decisive cancel                     — cancel the pending decisive marker
scene decisive status                     — show pending decisive marker
```

Example: `scene round strict quorum=70 cap=2 lock=on`

No business logic lives in `CmdScene` — all routing is delegated to the Actions above.
Mode tokens (`open` / `pose_order` / `strict`) are mapped to `SceneRoundMode` values by
`_parse_round_args`. Lock values: `on` / `true` / `yes` / `1` → True; anything else → False.

#### Decisive checks (#1748)

A GM may mark the next graded social check in a scene as **decisive** for a
linked `Beat` (predicate type `OUTCOME_TIER`). When that check resolves, its
`CheckOutcome` propagates to `record_outcome_tier_completion` — the same seam
combat encounters and mission completions use. Marker creation also activates
stakes contracts on the scene's staked beats (the freeform-scene equivalent of
encounter creation). See ADR-0128.

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

## UI Composition — `/game` One Play Surface (#2156)

Before #2156, the scene toolset (threading, action attachment, places, consent,
composer modes) was built but mounted only on the `/scenes/:id` record page; the
live `/game` view rendered a flat monospace log with no threading. `/game` is now
the one play surface — the full toolset composes there, and `/scenes/:id` remains
the unchanged record/detail page (`SceneInteractionPanel`).

**`GamePage`** (`frontend/src/game/GamePage.tsx`) is the composition root: it
derives the active session's `sceneId`/`roomName`, calls `useSceneInteractions` +
`useThreading` **once**, and threads the results down as props to
`ConversationSidebar` (left column), `GameWindow` (center feed + composer), and the
scene toolset (`ActionPanel`, `PlaceBar`, `ConsentPrompt`, `CharacterCardDrawer`) —
no child re-fetches the same scene/roster data.

**Feed presentation:** `PoseUnit` (`frontend/src/scenes/components/PoseUnit.tsx`)
renders each interaction as a chat bubble — avatar thumbnail, author, timestamp,
`FormattedContent`-rendered prose, and reactions — never monospace/terminal
styling (ratified presentation bar; terminal-style rendering on the primary feed is
a defect, not a variant). `GameWindow` renders this structured bubble feed plus
`SystemLane` (muted, collapsible system/channel/error strip) whenever the active
session has a scene; with no active scene it falls back to the legacy raw
`ChatWindow` log (`frontend/src/game/components/ChatWindow.tsx`). This restyle also
closes the markdown-rendering gap the #2155 audit flagged: the feed now renders
`FormattedContent`, so `RichTextInput`'s markdown output actually displays as
formatted prose instead of raw text.

**Threading + per-thread unread:** `ConversationSidebar` renders `ThreadSidebar` +
`ThreadFilterModal` from the `ThreadingState` `GamePage` composes, falling back to
a static "Room" button with no active scene. Per-thread unread counts are backed by
`Session.threadLastSeen` (per-thread last-seen **interaction ids**, persisted in
Redux via `markThreadSeen`) rather than stubbed to 0. A thread key with no
last-seen entry — i.e. a thread that's new since the session started — falls back
to `Session.sceneBaselineId`, a single scene-load baseline scalar set once via
`setSceneBaseline`; this is what lets a brand-new mid-session thread badge
correctly as unread from its first message, rather than needing its own baseline
established retroactively. Both `GamePage`'s baseline-capture effect and its
threading-filter/mute reset (`useThreading.resetForNewScene`) are keyed on
`[active, sceneId]`, so a puppet switch or scene change never strands a stale
filter/mute or wipes an already-baselined puppet's accumulated unread (the
baseline gate reads the per-puppet Redux `sceneBaselineId` directly, not a
single scalar ref). With neither a per-thread entry nor a baseline (e.g.
`/scenes/:id`, which passes no threading options at all), unread is 0 — unchanged
behavior for the record page.

**Character-card drawer:** clicking a `PoseUnit` avatar opens `CharacterCardDrawer`
(`frontend/src/game/components/CharacterCardDrawer.tsx`) in place (a `Sheet`
drawer over the conversation, not a page navigation) with Friend/Whisper quick
actions. **Privacy rule:** the persona payload carried by an `Interaction` has no
roster-entry or character-sheet id — only id/name/thumbnail — deliberately, so a
disguised or temporary persona can't be de-anonymized through the card. The drawer
resolves identity **only** via the public `AllowAny` roster search
(`useRosterEntryByNameQuery`, the same endpoint `RosterListPage` uses) and requires
an exact name match; no match (disguise, temporary persona, unlisted character)
renders name + avatar + a "not on the public roster" notice with no sheet data and
no `FriendButton`. Never resolve through `receiver_persona_ids`, scene
participation, or any other non-public linkage.

**Backend — pose co-location + place presence:** `PoseSubmitSerializer.validate`
(`interaction_serializers.py`) rejects (400) a pose submitted with a `scene_id`
whose scene has a room (`scene.location` set) that doesn't match the actor
character's current location — a wrong-room pose is now a validation error instead
of silently recording under the wrong scene. A scene with no location (`location`
is `None`) skips the check. `PlaceSerializer.viewer_is_present`
(`place_views.py`) is a `SerializerMethodField` reporting whether one of the
requesting account's owned personas has a `PlacePresence` row at that place;
memoized per serializer instance so a places-list response shares one owned-persona
lookup across all rows instead of re-querying per row. Scene poses submitted from
`/game` take the REST `submit-pose` path, keyed by `scene_id` — a pose belongs to
a scene, not a room, so this is unrelated to room id.

**Pose/action authorship is the worn face, derived server-side (#981 audit fix):**
the client's `persona_id`/`initiator_persona` only *selects the acting character*
(ownership-validated); `submit_pose`, the action-request create path, and the
technique-cast create path all re-derive the recorded persona via
`active_persona_for_sheet`, and `record_interaction`'s no-persona fallback (the
telnet/WS path) does the same — never `primary_persona` directly, so a client
passing the primary id can never unmask a worn ESTABLISHED alt or TEMPORARY mask.
Frontend mirrors this with `actingPersonaId()` (`frontend/src/roster/persona.ts`)
everywhere a persona id feeds an IC write or self-matching read (attention
routing, own-pose exclusion).

**Places query room-id vs scene-id (fold-in fix, unrelated to the above):**
`PlaceBar`'s `sceneId` prop is actually used as the ROOM id by
`fetchPlaces(?room=)` (confirmed by reading `PlaceBar.tsx` + `actionQueries.ts`)
— so `/game` derives `placesRoomId`/`isAtPlace` from the scene's room
(`roomData.id`), not the scene id. `SceneDetailPage` still passes the scene id
there; that's a separate, pre-existing latent bug on that page, left untouched
by this slate.

**#2165 conversation tabs:** `/game` can keep several conversations open at once
— the room feed as a permanent anchor plus a closable tab per broken-out
place/whisper/target thread (`ConversationTabStrip.tsx`, rendered above the feed
in `GameWindow`). Tab state (`openThreadTabs`/`activeThreadTab`) lives in
`gameSlice`'s per-character `Session`, one tab set per session. The
`ConversationSidebar` is the **open-a-tab surface**: clicking a thread row opens
or focuses its tab; clicking the room row or "All" re-anchors the strip back to
the room feed. The composer's audience is **derived from the active tab and
locked**, never stored independently — `tabKeyToComposerMode` (in
`threadToComposerMode.ts`) translates the active tab's key into a locked
`ComposerMode` every render, which is the mis-send guard (a stale composer
audience surviving a tab switch is the failure mode this closes). The open-tab
layout is persisted client-locally per character+scene (thread **keys** only,
never message content) via `threadTabsStorage.ts`'s `localStorage` helpers, and
`gameSlice` resets both tab fields whenever the session's scene id actually
changes, since a tab pointing at a previous scene's thread set is unsafe to keep
open.

### #2166 multi-character attention

Cross-character attention routing so a player running several PCs at once
doesn't have to poll every tab for background activity — all of it client-side
and per-PC scoped, no new server data or write path.

**Two-tier attention derivation:** `sessionAttention(session, personaId)`
(`frontend/src/game/attention.ts`) is a pure, selector-side function reusing
#2165's `getThreadKey`/`countUnread` grouping against
`threadLastSeen`/`sceneBaselineId` — the same threshold rule the tab strip's
own unread badges already use, just re-run per background session instead of
per open tab. `direct` = unread on `whisper:*` threads plus `target:*` threads
that include that session's `personaId` (an @-target, duel challenge, or
consent request aimed at that persona specifically); `ambient` = any other
thread unread, or the legacy `session.unread` scalar. `GameTopBar`'s alt
avatars and `GameWindow`'s puppet tab bar both render the tier as a red
numeric badge (direct) or a muted dot (ambient) — the **active** character is
always excluded (its own attention already lives in `ConversationTabStrip`'s
per-tab badges), so nothing double-counts.

**Whisper toasts:** `handleInteractionPayload.ts` (`frontend/src/hooks/`)
fires one toast when a whisper lands on a session that isn't the active one
and wasn't authored by that session's own persona, deduped per
`character:interactionId` (a shared whisper delivered to two of the player's
own characters toasts once per character, not once total). Clicking the toast
switches the active session, opens the whisper's thread tab, and navigates to
`/game` — the same switch-through a player would do by hand.

**Right-character prompt dispatch:** duel challenges and scene action
(consent) requests addressed to a background character surface and act **as
that character**, not the currently-active one. `DuelChallengeNotifier`
(`frontend/src/combat/`) already polled account-wide; the fix was resolving
each challenge's `challenged` CharacterSheet id against the account's roster
and binding `useDispatchPlayerAction` to that character per-toast, so Accept/
Decline dispatch under the addressed character's id even while a different PC
is active. `ConsentAttentionNotifier` (`frontend/src/scenes/components/`) is
the same shape for scene action requests: it polls
`GET /api/action-requests/?status=pending&role=incoming` (see the `role`
filter under Action Requests below), resolves the request's `target_persona`
against the roster's `primary_persona_id`/`active_persona_id`, and toasts
"Consent request for `<Character>`: `<action>` from `<initiator>`" with no
accept/deny in the toast itself — clicking only switches to (or starts a
session for) the addressed character and navigates to `/game`, where the
existing per-scene `ConsentPrompt` owns the graded response.

**Speaking-as chip:** every composer (`CommandInput.tsx`, on both `/game` and
`/scenes/:id`) renders a standing avatar+name chip naming whichever character
is about to speak, even for single-character players — a permanent answer to
"who am I talking as right now" independent of the attention badges above.

**Per-PC scoping ("Never out alts", `docs/roadmap/design-tenets.md`):** all of
the above is derived client-side from data the account already legitimately
holds (its own sessions' cached interactions, its own roster's persona ids,
requests already scoped server-side to `get_account_personas`) — no new
account-wide field is added to any payload another player can see, and
nothing here merges or unions what two of an account's characters can
perceive.

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
