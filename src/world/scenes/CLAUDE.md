# Scenes System - Roleplay Session Recording & Identity

Captures and manages roleplay sessions with participant tracking, interaction recording, story integration,
the unified Persona identity system, and non-combat scene rounds.

## Key Files

### `models.py`
- **`Scene`**: Primary scene entity with title, status, location, summary, privacy_mode
- **`SceneParticipation`**: Account participation tracking in scenes. `is_gm` is the single
  predicate every GM-combat surface gates on (`Scene.is_gm`, `_actor_may_gm_encounter`,
  `IsEncounterGMOrStaff`). Three writers: `_enroll_lead_gm_on_scene`
  (`world/stories/services/crossover.py`, #2113) for crossover Lead GMs;
  `scene_admin_services.enroll_present_table_gms` (#2113) — auto-flags a present account
  that owns an ACTIVE `GMTable` with an *other* present character holding an active
  `GMTableMembership` on it; called from `StartSceneAction.execute()` on both the
  new-scene and mid-scene-join paths; and `CreateBattleAction.execute()`
  (`actions/definitions/battles.py`, #2010) — grants the staging GM `is_gm` on the new
  Battle's backing Scene via the same `update_or_create` pattern, so the battle-scoped
  staging actions' `_actor_may_gm_battle` recognizes this GM as the battle's own, not
  merely staff. `GrantSceneGMAction` (`scene gm <name>`,
  `actions/definitions/scenes.py`) is the fallback explicit grant for cases
  auto-detection can't reach, gated on `actor_can_administer_scene` + target `GMProfile`.
  See "Scene Administration" in `docs/systems/scenes.md` for the full design.
- **`Persona`**: Unified identity model with PersonaType (PRIMARY/ESTABLISHED/TEMPORARY/ALTERNATE). FK to CharacterSheet
  (source of truth); partial unique constraint ensures one PRIMARY per sheet
- **`PersonaDiscovery`**: Records that a character discovered two personas are the same person
- **`Block`** (#1278): one player blocking another, persona-scoped by default (`blocker_persona` ↔
  `blocked_persona`) with an `account_level` opt-in; keyed on `PlayerData` so it follows the person
  across re-rosters. Resolution + lifecycle in `block_services.py` (`coded_block_active`,
  `sheet_blocked_for_viewer`, `hidden_persona_ids_for_viewer`, `lift_block`, `finalize_expired_blocks`).
  Wired into the profile gate (404), the scene target picker, and feed visibility. The cron-clear
  (`finalize_expired_blocks`, wired into `game_clock` via `scenes.block_finalize`) is done.
  Supersedes the removed `evennia_extensions.PlayerBlockList`. Remaining: the awareness/"Character Has
  You Blocked" surface (#2086).
- **`Mute`** (#1278): the lighter, **one-way** sibling of Block — a player filters a persona out of
  their own view (IC and/or OOC), reversible, no enforcement, the muted party never aware.
  `mute_services.py` (`muted_persona_ids_for_viewer`, `set_mute`, `unmute`); the IC side is wired into
  the scene feed (muted personas skipped). The OOC channel, the "actions still show without text"
  refinement, the opt-in reveal, and the "N hidden" feed divider are follow-ups (#2087).
- **`BlockContactFlag`** (#1278): the anti-derivation awareness layer. When a *blocked* player reaches the
  blocker via another identity (circumvention the coded block can't prevent without leaking the alt),
  `block_services.flag_blocked_contact_attempt` records it for staff (anchored on accounts + personas;
  zero signal to either player). Hooked into `action_services.create_action_request` and the direct
  communication actions (`WhisperAction`, directed `SayAction`/`PoseAction`, `CmdPage`). Staff triage
  via admin. Remaining: the player-facing generic "Character Has You Blocked" warning (#2086).
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
  `anti_spam_seconds`, `abandonment_grace_rounds` (#1479: N action-driven beats an abandoned
  downed victim waits for rescue before their fate resolves; default 2),
  `sudden_harm_interpose_threshold` (#1316: minimum out-of-combat sudden-harm amount that
  justifies holding for a reactive Interpose beat instead of applying it immediately; default 10).
  Retrieved via `get_scene_round_defaults_config()` (get-or-create pattern).
- **`SceneActionDeclaration`**: Per-round ledger of participant actions. `is_immediate=True` for
  OPEN/POSE_ORDER resolved actions; `is_immediate=False` for deferred STRICT declarations. Carries
  `target_persona` FK and `is_pass` bool. No unique-per-round constraint — multiple actions per round
  are allowed (up to `max_actions_per_round`). `succor_target` FK (`SceneRoundParticipant`, #1744)
  names the ally this declaration shelters from a round-ticked hazard, paired with a cached
  `succor_resolution` float (this round's graded Succor outcome, read by `get_cover_for`).
  `interpose_target` FK (`SceneRoundParticipant`, #1316) names the ally this declaration guards
  against out-of-combat sudden harm — the scene-round sibling of `succor_target` — but has no
  paired resolution-cache field: `resolve_pending_interpose_harm` reads it directly at round
  resolution instead of caching an outcome onto the declaration row.
- **`SceneRoundParticipant`**: A character taking turns in a `SceneRound`.
- **`PendingSuddenHarm`** (#1316): a one-shot out-of-combat damage payload held pending a
  reactive Interpose beat. `target_sheet` (FK `CharacterSheet` — multiple unresolved rows may
  exist per target at once, e.g. a single Consequence with two DEAL_DAMAGE effects against the
  same target), `scene_round` FK (the bootstrapped DANGER round bound to resolve it), `amount`,
  `damage_type` (nullable FK `DamageType`), `source_description`. Created by
  `world.scenes.sudden_harm.arm_or_apply_sudden_harm` when a bystander is present and the harm
  clears `SceneRoundDefaultsConfig.sudden_harm_interpose_threshold`; resolved and deleted by
  `world.scenes.sudden_harm.resolve_pending_interpose_harm` at that round's resolution.

- **`Boon`** (#2540, `boon_models.py` + `boon_services.py`): the payload of a structured social ask
  ("ask a head/NPC for a thing, backed by a social roll"), attached 1:1 to a `SceneActionRequest`.
  Fields: `kind` (`BoonKind`: MONEY/HELD_ITEM/VAULT_ITEM/DEED), `amount`, `item_instance`, `deed_text`,
  `fulfilled_at`. **Slice 2 wired the full loop:** `create_action_request(boon=BoonAsk(...))`
  validates eligibility up front (`validate_boon_ask`, dial 1 — uncoverable money / unheld item /
  empty deed / vault-stub asks are rejected before any row exists) and persists the `Boon` row
  BEFORE NPC auto-resolve, so the defender sees the ask pre-consent. The `boon` **resolver**
  (`register_resolver`, imported by `ScenesConfig.ready`) fires on both consent paths — NPC
  auto-accept and piloted accept — fulfilling on success (`fulfill_boon`; MONEY via
  `currency.transfer`, DEED RP-only, HELD_ITEM/VAULT_ITEM transfer are follow-ups) and charging
  the per-Boon **stacking** affection cost (`BOON_AFFECTION_COST` PLACEHOLDER, boon-keyed
  `AffectionShift` — serial asks wear out welcome; the hit never decays). **Fulfillment must NOT
  ride `BoonAction.execute()`** (consent paths never call it — the Blackmail-mint asymmetry) nor a
  seeded `SHIFT_AFFECTION` effect (the consent path's `ResolutionContext` is sceneless).
  `npc_boon_tier_shift` is the mandatory dial-2 NPC relative-cost band
  (`resolved_base_difficulty(extra_tier_modifier=…)`); a piloted defender's difficulty choice
  rules — never band-shifted. Seeds: `Boon` template (`world/seeds/social_actions.py`) + `boon`
  consent category under `antagonism` (`world/seeds/consent.py`).

### `constants.py`
- **`BoonKind`** (`TextChoices`, `action_constants.py`): what a Boon asks for (MONEY / HELD_ITEM /
  VAULT_ITEM / DEED).
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
  - `get_cover_for(target, damage_type) -> float` (#1744): the scene-round sibling of
    `CombatRoundContext.get_cover_for` — resolves (and caches on
    `SceneActionDeclaration.succor_resolution`) this round's Succor cover multiplier for
    `target`. Returns `1.0` (no cover) when `target` has no ACTIVE participant or no
    `SceneActionDeclaration.succor_target` names them this round. Mirrors the combat side's
    caching contract but has no fatigue-charge step (scene rounds have no combat fatigue seam).

### `succor_content.py` (scenes)
Scene-round Succor challenge-binding (#1744) — the scene-round equivalent of combat's
`_ensure_succor_challenges`, keyed off `SceneActionDeclaration.succor_target` instead of
`CombatRoundAction`. No prior scene-round "bind a reactive challenge" plumbing existed before this.
- `ensure_succor_challenges_for_round(scene_round)`: binds a Succor `ChallengeInstance` to each
  protected ally declared this round; called from `resolve_scene_round` right before
  `_resolve_scene_declarations`, so the challenge exists in time for `get_available_actions` to
  surface it when the declared Succor action itself resolves in initiative order. Logs
  `logger.warning` and no-ops when the Succor `ChallengeTemplate` isn't seeded (mirrors
  `world.combat.services._ensure_succor_challenges`'s equivalent branch).

### `sudden_harm.py` (#1316)
Out-of-combat sudden-harm arming — the non-combat sibling of combat's Interpose. Mirrors
`world.areas.positioning.plummet.begin_plummet`'s bystander-present/absent branch: alone (or below
the configured significance threshold), harm resolves immediately, byte-identical to the pre-#1316
behavior; with a bystander present, the harm is held (`PendingSuddenHarm`) and a DANGER round is
bootstrapped so they get a genuine declare-then-resolve window before it lands.
- `arm_or_apply_sudden_harm(target, amount, damage_type, *, source_description="")`: the branch
  entrypoint, called from `world.mechanics.effect_handlers._deal_damage`. Below
  `sudden_harm_interpose_threshold`, or with nobody present who could plausibly interpose
  (`_potential_interposer_present`), applies immediately via `apply_resolved_damage`. Otherwise
  binds an Interpose `ChallengeInstance` to the target (`_bind_interpose_challenge`) and
  bootstraps (or rides) a scene round via `ensure_round_for_acute_condition`, then creates the
  `PendingSuddenHarm` row. Degrades to immediate resolution — logging a warning — if the Interpose
  `ChallengeTemplate` isn't seeded or no room is available to hold a round in.
- `resolve_pending_interpose_harm(scene_round)`: called from `resolve_scene_round` right after the
  END tick. For each `PendingSuddenHarm` bound to the round's ACTIVE participants: looks up this
  round's `interpose_target` declaration naming the victim (if any), resolves it via the unchanged
  `world.combat.services.dispatch_interpose` (mutates a `DamagePreApplyPayload` in place per the
  graded outcome, mirroring combat's `_try_interpose`), applies the resulting amount via
  `apply_resolved_damage`, then deactivates the bound Interpose `ChallengeInstance` and deletes the
  pending row. No declaration this round -> full harm lands (the AFK-safe default, inherited for
  free from the existing quorum-gated round system).

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
- `resolve_scene_round(scene_round)`: Unconditional resolver — binds this round's Succor challenges
  (`ensure_succor_challenges_for_round`, #1744), runs declared CHALLENGE actions in
  initiative order, fires the end-round tick (which advances acute conditions — DoTs, bleed-out, plummet),
  resolves any pending out-of-combat sudden-harm Interpose beats (`resolve_pending_interpose_harm`,
  #1316), then either advances to the next round or **auto-ends**. **Succor and Interpose
  declarations are excluded from `_resolve_scene_declarations`'s generic challenge-resolution sweep
  and its end-of-sweep delete** (#1744 bugfix, extended to Interpose in #1316) — a pending Succor
  row has `challenge_instance=None` (identified instead by `succor_target`) and a pending Interpose
  declaration is identified by `interpose_target`, so feeding either into the CHALLENGE sweep would
  crash on `req.challenge_instance.location`, and deleting a Succor row early would erase
  `SceneActionDeclaration.succor_resolution`'s cache before `get_cover_for` (called from the END
  tick) can ever read it. A leftover Succor or Interpose row from a past round is harmless —
  `round_number` advances every round and both readers only match the current one. (a `start_reason==DANGER` round COMPLETES once
  `_danger_persists` is False — no ACTIVE participant still carries an acute danger condition). **AFK
  own-peril skip (#1480):** a present `can_act` participant who did NOT declare this round (swept as an
  implicit pass by quorum completion) is excluded from the END-tick target set, so their OWN acute
  conditions do not advance from a round they didn't engage in (ADR-0004 — an AFK character is not harmed
  while away). Declared, absent, and present-`not can_act` (unconscious) participants tick as before.
  **Downed-victim narrowing (#1479):** a DOWNED victim (present, `not can_act`, carrying an active
  acute-peril condition — Bleeding Out / Plummeting) advances on the END tick ONLY when a hostile party
  drove the round (`world.vitals.peril_resolution.hostile_drove_round` — the peril's `source_character`
  is a participant who declared this round). Otherwise the peril HOLDS (excluded from the tick) and the
  victim's acute-peril `ConditionInstance.abandoned_since_round` is stamped (once) when a potential
  rescuer is present (`potential_rescuer_present`); a later hostile-driven round clears the marker.
  `_resolve_downed_victim_peril` snapshots these decisions BEFORE `_resolve_scene_declarations` deletes
  the declaration rows. A consequence: a danger round with an abandoned downed victim resolves (advances)
  but does NOT auto-complete while the held peril persists.
  **Abandonment resolution (#1479 Task 8):** after the END tick, `_resolve_abandonment_grace` resolves
  any held (abandoned, non-advancing) downed victim who has waited out the grace window
  (`round_number - abandoned_since_round >= SceneRoundDefaultsConfig.abandonment_grace_rounds`) via the
  source-appropriate abandonment pool (`world.vitals.services.resolve_abandonment` →
  `select_abandonment_pool` → the shared death-gated `_resolve_peril_via_pool` core). Done before the
  auto-end check so a resolved peril lets the danger round complete instead of freezing in limbo.
- `resolve_solo_abandoned_victims(room, *, departing=None)`: **solo-case (#1479 Task 8)** — when a
  departure (wired into `typeclasses.rooms.Room.at_object_leave`) removes the LAST potential rescuer
  from a room, any still-downed victim there has their fate resolved IMMEDIATELY via the same
  `resolve_abandonment` path. `at_object_leave` fires before the mover leaves `room.contents`, so
  `departing` is excluded from the rescuer check (`potential_rescuer_present(..., exclude_character_id=)`).
  A single cheap room-bound query short-circuits ordinary rooms. Rescue (the bleed-out cleared via
  `remove_condition`/`perform_treatment`) before either trigger leaves no acute-peril instance, so
  `resolve_abandonment` no-ops — rescue beats the check.
- `maybe_finish_empty_scene(room, *, leaving=None)` (#1361): the scene-lifecycle
  sibling of `resolve_solo_abandoned_victims` — finishes the room's active
  `Scene` (via `finish_scene_full`) once no PC other than `leaving` remains in
  `room.contents`. Wired into `Room.at_object_leave` (movement) and
  `Character.at_post_unpuppet` (disconnect, after Evennia's own base-class
  relocation — see typeclasses/characters.py — has already removed the
  character from the room). **Skips** any scene with a live (`completed_at`/
  `concluded_at` is null) `CombatEncounter` or `Battle` attached — that
  scene's lifecycle belongs to the encounter/battle outcome, not room
  emptiness, and such scenes lack the account/participant data
  `finish_scene_full`'s broadcast step needs (a real CI-caught crash, not a
  theoretical concern). Follow-up: #1899 (combat/mission disconnect policy).
- `ensure_round_for_acute_condition(character_sheet) -> SceneRound | None`: ensures an active scene round
  for the character's room (enrolling everyone present). When none is active, creates a STRICT
  `SceneRound(start_reason=DANGER)`; when one already exists (any mode), the peril rides it. Caller
  guarantees the character is not in active combat. (Renamed from `auto_start_or_extend_danger_round`.)
- `maybe_resolve_scene_round(scene_round)`: Resolves only when quorum-gated completion is met.
- `declare_succor_scene(participant, ally) -> SceneActionDeclaration` (#1744): the scene-round
  sibling of `world.combat.services.declare_succor` — always names a specific ally (no "any
  ally" path, same rationale). Writable during an open STRICT declaration window; upserts the
  round's deferred `SceneActionDeclaration` for `participant`, setting `succor_target=ally` and
  resetting `succor_resolution` to `None`.
- `declare_interpose_scene(participant, ally) -> SceneActionDeclaration` (#1316): the scene-round
  sibling of `world.combat.services.declare_interpose` — named-ally only (mirrors
  `declare_succor_scene`'s #1744 narrowing; no fatigue charge, scene rounds have no combat fatigue
  seam). Writable during an open STRICT declaration window; upserts the round's deferred
  `SceneActionDeclaration` for `participant`, setting `interpose_target=ally`.
- `scene_round_is_complete(scene_round) -> bool`: True when enough present ACTIVE participants who *can
  act* have a deferred (`is_immediate=False`) declaration for the current round — the threshold is
  `ceil(advance_quorum_pct / 100 × present_active_count)` (the same field POSE_ORDER uses; at 100 it
  reduces to unanimity, so a GM/staff can still require everyone). Absent and present-but-`not can_act`
  participants are implicit passes (never block); an undeclared present `can_act` participant counts
  toward the denominator but not the declared count, so a quorum below 100 lets the round resolve without
  them — ending the single-AFK-participant deadlock (#1480) without a wall clock. The AFK participant's
  own peril is skipped separately at resolution (see `resolve_scene_round`).

### `views.py`
- **`SceneViewSet`**: Scene CRUD operations and filtering
- **`PersonaViewSet`**: Persona management (read + actions; **not** a `ModelViewSet` — the raw
  create was removed, #1127). `set_active` dispatches `SetActivePersonaAction`
  (key `"set_active_persona"`, `actions/definitions/personas.py`) via `dispatch_player_action`
  — the same seam the telnet `CmdPersona` uses. `set_active_persona` (service) remains the
  sole mutator of `CharacterSheet.active_persona`; the action wraps it.
  - **Designed creation (#1127):** `create-established` / `create-mask` POST actions are the only
    creation surface (telnet `persona create|mask` mirrors them). Both call the validated services
    `scenes.services.create_persona` (ESTABLISHED; capped by
    `settings.MAX_ESTABLISHED_PERSONAS_PER_SHEET`, staff bypass) and `create_mask` (TEMPORARY
    anonymous mask, optionally applying a #1110 disguise overlay + switching the worn face). PRIMARY
    is never created here. Creation copies **no** descriptors from sibling faces — the
    descriptor-never-auto-attach privacy invariant (#1109) holds structurally.
  - **Guise-Sheet authoring (#1682):** `set-profile` POST action — the web face of
    `scenes.services.set_persona_profile` (sole mutator; PRIMARY rejected). Ownership-gated
    like `set_active` (own-sheet personas only, uniform rejection); absent fields stay
    untouched, blank fields clear. `PersonaSerializer` exposes read-only `guise_concept` /
    `guise_quote` / `guise_personality` / `guise_background` so the switcher's
    `GuiseSheetDialog` (`frontend/src/game/components/`) prefills. Telnet parity:
    `persona profile <name> …` (#1270).
- **`SceneSummaryRevisionViewSet`**: Summary revision management

### `friend_views.py` (#1727, #2170)
- **`FriendshipViewSet`**: the web face of the OOC friends list (`friend_services.py`) —
  list/add/remove. `list` returns the player's friendships (made by any of their characters).
  `create` takes **`viewer`/`friend` as `RosterEntry` pks** (web clients speak character ids, not
  tenure ids) plus `all_characters`; the view resolves each to its `current_tenure` server-side and
  calls `add_friend` / `add_friend_all_characters`. Tenure-scoped + alt-private, mirroring the
  Block/Mute control API. Telnet parity is `CmdFriend`/`CmdUnfriend`/`CmdFriends`. React surface:
  `frontend/src/friends/` (`FriendsTab` self-only tab + `FriendButton` on other sheets).
- **`RivalryViewSet`** (#2170): the web face of rival declarations (`/api/scenes/rivals/`) —
  list/declare/withdraw, same shape as friendships (`viewer`/`rival` as `RosterEntry` pks,
  resolved to tenures server-side, calling `declare_rival`). Double opt-in: the list queryset
  annotates `is_mutual` (an `Exists` on the reciprocal row) and the create response stamps it,
  so the client can render "mutual rivals" vs "awaiting their declaration"; a DELETE removes
  only your own side. Telnet parity is `CmdRival`/`CmdUnrival`/`CmdRivals`. React surface:
  `RivalButton` (`frontend/src/friends/components/`) on another character's sheet page + card
  drawer, next to the `FriendButton`.

### `interaction_views.py`
- **`InteractionViewSet`**: Interaction read + delete + mark_private
- **`InteractionFavoriteViewSet`**: Toggle favorites — routes through
  `world.scenes.reaction_toggle_services.toggle_interaction_favorite` (the sole mutator), the same
  seam telnet `CmdReact` reaches via `ToggleFavoriteAction` (#1341).
- **`InteractionReactionViewSet`**: Toggle reactions — routes through
  `world.scenes.reaction_toggle_services.toggle_interaction_reaction` (the sole mutator), the same
  seam telnet `CmdReact` reaches via `ToggleReactionAction` (#1341).

### `reaction_views.py` (#904)
- **`ReactionWindowViewSet`**: action-only viewset over `ReactionWindow`/`WindowReaction`
  (`reaction_models.py`). `react` (detail POST) records a reaction on an existing window via
  `react_to_window`; `react-to-interaction` (custom list POST, #911) lazily opens a
  `lazy_open` window kind (e.g. `kudos`) on an `Interaction` that has none yet via
  `react_to_interaction`, then records the reaction in one call. Reads ride the interaction
  feed — windows serialize inline on their event; all eligibility lives in the two services.
  Frontend caller (#2031): `ReactionStrip`'s first-kudos chip
  (`frontend/src/scenes/components/ReactionStrip.tsx`) calls `POST
  /api/reaction-windows/react-to-interaction/` with `kind: "kudos"` when the pose has no
  kudos-kind window yet (including the previously-null empty-windows case); once a kudos
  window exists the normal per-window row takes over and the chip disappears.

### `serializers.py`
- Scene and persona serialization for API responses
- Participant data serialization

### `filters.py`
- Scene filtering by status (Active/Completed/Upcoming)
- Persona filtering by scene, character, type
- Search by participants, location

### `permissions.py`
- Participation-based access control
- Privacy controls for disguised participation

## Key Classes

- **`Scene`**: Contains participants and interactions
- **`SceneParticipation`**: Tracks account involvement in scenes
- **`Persona`**: Unified identity with `persona_type` field (PRIMARY/ESTABLISHED/TEMPORARY/ALTERNATE). Has
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
| | resolves batch when quorum-gated completion is met (`ceil(advance_quorum_pct/100 × present_active)`,
| | #1480 — not unanimity) or a GM force-resolves. An undeclared present `can_act` participant's own |
| | peril is skipped on the END tick (ADR-0004). Danger |
| | rounds (#1466) are STRICT: the peril ticks at resolution; the round auto-ends when it clears. |

`SceneRoundDefaultsConfig` (singleton pk=1, accessed via `get_scene_round_defaults_config()`) lets
staff tune `default_mode`, `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`,
and `anti_spam_seconds` without a code deploy.
