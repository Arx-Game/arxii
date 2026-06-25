# Scenes System - Roleplay Session Recording & Identity

Captures and manages roleplay sessions with participant tracking, interaction recording, story integration,
the unified Persona identity system, and non-combat scene rounds.

## Key Files

### `models.py`
- **`Scene`**: Primary scene entity with title, status, location, summary, privacy_mode
- **`SceneParticipation`**: Account participation tracking in scenes
- **`Persona`**: Unified identity model with PersonaType (PRIMARY/ESTABLISHED/TEMPORARY). FK to CharacterSheet
  (source of truth); partial unique constraint ensures one PRIMARY per sheet
- **`PersonaDiscovery`**: Records that a character discovered two personas are the same person
- **`Block`** (#1278): one player blocking another, persona-scoped by default (`blocker_persona` ↔
  `blocked_persona`) with an `account_level` opt-in; keyed on `PlayerData` so it follows the person
  across re-rosters. Resolution + lifecycle in `block_services.py` (`coded_block_active`,
  `sheet_blocked_for_viewer`, `hidden_persona_ids_for_viewer`, `lift_block`, `finalize_expired_blocks`).
  Wired into the profile gate (404), the scene target picker, and feed visibility. Supersedes the removed
  `evennia_extensions.PlayerBlockList`. Remaining: the awareness/"Character Has You Blocked" surface +
  the cron job.
- **`Mute`** (#1278): the lighter, **one-way** sibling of Block — a player filters a persona out of
  their own view (IC and/or OOC), reversible, no enforcement, the muted party never aware.
  `mute_services.py` (`muted_persona_ids_for_viewer`, `set_mute`, `unmute`); the IC side is wired into
  the scene feed (muted personas skipped). The OOC channel, the "actions still show without text"
  refinement, the opt-in reveal, and the toggle UI are follow-ups.
- **`BlockContactFlag`** (#1278): the anti-derivation awareness layer. When a *blocked* player reaches the
  blocker via another identity (circumvention the coded block can't prevent without leaking the alt),
  `block_services.flag_blocked_contact_attempt` records it for staff (anchored on accounts + personas;
  zero signal to either player). Hooked into `action_services.create_action_request`. Staff triage via
  admin. Remaining contact vectors (targeted poses/whispers) + the player-facing generic "Character Has
  You Blocked" warning are follow-ups.
- **`Interaction`**: Atomic IC interaction record (pose, say, whisper, etc.) with privacy controls
- **`InteractionFavorite`**: Private bookmarks for cherished RP moments
- **`InteractionReaction`**: Emoji reactions on interactions
- **`InteractionTargetPersona`**: Explicit IC targets for thread derivation
- **`SceneSummaryRevision`**: Collaborative summary editing for ephemeral scenes
- **`SceneRound`**: Non-combat round/turn structure anchored to a room. Fields: `mode` (`SceneRoundMode`),
  `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`. `mode` and `start_reason` are
  fully orthogonal — the persistence layer never rewrites one from the other (#1466). Danger is no longer
  a round *type*: an acute peril ensures a STRICT `SceneRound(start_reason=DANGER)` via
  `ensure_round_for_acute_condition`, ticked at round resolution like any STRICT round. One active round
  per room (UniqueConstraint on non-COMPLETED status).
- **`SceneRoundDefaultsConfig`** (singleton pk=1): staff-tunable defaults for new scene rounds. Fields:
  `default_mode`, `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`,
  `anti_spam_seconds`. Retrieved via `get_scene_round_defaults_config()` (get-or-create pattern).
- **`SceneActionDeclaration`**: Per-round ledger of participant actions. `is_immediate=True` for
  OPEN/POSE_ORDER resolved actions; `is_immediate=False` for deferred STRICT declarations. Carries
  `target_persona` FK and `is_pass` bool. No unique-per-round constraint — multiple actions per round
  are allowed (up to `max_actions_per_round`).
- **`SceneRoundParticipant`**: A character taking turns in a `SceneRound`.

### `constants.py`
- **`SceneRoundMode`** (`TextChoices`): `OPEN` (immediate, unbounded), `POSE_ORDER` (immediate,
  quota-gated — quorum advances the round), `STRICT` (declare-then-batch-resolve).
  Social rounds default to `POSE_ORDER`; danger rounds are `STRICT` (#1466).

### `round_context.py`
- **`SceneRoundContext`**: `RoundContext` implementation backed by a `SceneRound`.
  - `is_declaration_open`: `True` only when `mode==STRICT` and status is DECLARING. Danger rounds are
    STRICT, so they gather declarations like any other STRICT round (no special-case). POSE_ORDER and
    OPEN rounds resolve immediately — declarations are never gathered.
  - `is_repeat_blocked(actor, action_ref, target_persona)`: OPEN → always False; STRICT → True when the
    declaration window is closed; POSE_ORDER → True when `actions_this_round >= max_actions_per_round`
    or `per_target_repeat_lock` and the target was already hit this round.
  - `record_immediate_action(actor, action_ref, target_persona)`: No-op for OPEN/STRICT; for POSE_ORDER
    writes a ledger row via `record_pose_order_action` and calls
    `advance_pose_order_round_if_quorum`.

### `round_services.py`
Key service functions for scene round lifecycle:
- `actions_this_round(scene_round, participant) -> int`: Declaration count for a participant this round.
- `distinct_actors_this_round(scene_round) -> int`: Number of distinct participants with declarations.
- `record_pose_order_action(scene_round, participant, target_persona=None)`: Write an `is_immediate=True`
  ledger row for a POSE_ORDER action.
- `advance_pose_order_round_if_quorum(scene_round) -> SceneRound`: Advance `round_number` when distinct
  actors ≥ `ceil(advance_quorum_pct / 100 × active_participant_count)`. Round stays DECLARING.
- `start_scene_round`, `advance_scene_round`, `end_scene_round`: Lifecycle transitions
  (BETWEEN_ROUNDS → DECLARING → RESOLVING → BETWEEN_ROUNDS → COMPLETED).
- `resolve_scene_round(scene_round)`: Unconditional resolver — runs declared CHALLENGE actions in
  initiative order, fires the end-round tick (which advances acute conditions — DoTs, bleed-out, plummet),
  then either advances to the next round or **auto-ends** (a `start_reason==DANGER` round COMPLETES once
  `_danger_persists` is False — no ACTIVE participant still carries an acute danger condition).
- `ensure_round_for_acute_condition(character_sheet) -> SceneRound | None`: ensures an active scene round
  for the character's room (enrolling everyone present). When none is active, creates a STRICT
  `SceneRound(start_reason=DANGER)`; when one already exists (any mode), the peril rides it. Caller
  guarantees the character is not in active combat. (Renamed from `auto_start_or_extend_danger_round`.)
- `maybe_resolve_scene_round(scene_round)`: Resolves only when presence-gated completion is met
  (every present ACTIVE participant who *can act* has a deferred declaration row).
- `scene_round_is_complete(scene_round) -> bool`: True when all present ACTIVE participants who *can act*
  have a deferred (`is_immediate=False`) declaration for the current round. Absent and present-but-`not
  can_act` participants (e.g. an unconscious bleeding victim) are implicit passes — they never block, so a
  conscious bystander's declaration alone can drive resolution (AFK-safety + no deadlock).

### `views.py`
- **`SceneViewSet`**: Scene CRUD operations and filtering
- **`PersonaViewSet`**: Persona management
- **`SceneSummaryRevisionViewSet`**: Summary revision management

### `interaction_views.py`
- **`InteractionViewSet`**: Interaction read + delete + mark_private
- **`InteractionFavoriteViewSet`**: Toggle favorites
- **`InteractionReactionViewSet`**: Toggle reactions

### `serializers.py`
- Scene and persona serialization for API responses
- Participant data serialization

### `filters.py`
- Scene filtering by status (Active/Paused/Finished)
- Persona filtering by scene, character, type
- Search by participants, location

### `permissions.py`
- Participation-based access control
- Privacy controls for disguised participation

## Key Classes

- **`Scene`**: Contains participants and interactions
- **`SceneParticipation`**: Tracks account involvement in scenes
- **`Persona`**: Unified identity with `persona_type` field (PRIMARY/ESTABLISHED/TEMPORARY). Has
  `character_sheet` FK to CharacterSheet (the source-of-truth anchor). `is_established_or_primary`
  property for permission checks. Hosts `display_ic` / `display_with_history` / `display_to_staff` helpers
- **`PersonaDiscovery`**: Stores raw discovery pairs; service functions handle resolution logic
- **`Interaction`**: Universal building block of RP recording with privacy tiers

## Three-Mode Round Framework (#1351)

Scene rounds support three action-gating modes (orthogonal to `start_reason`):

| Mode | Behavior |
|------|----------|
| `OPEN` | Every action resolves immediately, no quota. |
| `POSE_ORDER` | Actions resolve immediately; after `ceil(quorum_pct × active_count)` distinct actors |
| | have acted, `round_number` advances. Default for social rounds. |
| `STRICT` | Actions are declared into a ledger while `is_declaration_open`; the full round |
| | resolves batch when presence-gated completion is met or a GM force-resolves. Danger |
| | rounds (#1466) are STRICT: the peril ticks at resolution; the round auto-ends when it clears. |

`SceneRoundDefaultsConfig` (singleton pk=1, accessed via `get_scene_round_defaults_config()`) lets
staff tune `default_mode`, `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`,
and `anti_spam_seconds` without a code deploy.
