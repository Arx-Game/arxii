# RP Interaction & Scenes

**Status:** in-progress
**Depends on:** Checks, Relationships, Magic (aura farming)

## Overview
The core RP experience — how players interact in scenes. Arx II replaces arcane telnet commands with a modern web interface that lets players attach mechanical actions to their poses, react to each other's writing, and build skills and relationships during what would otherwise be trivial social scenes.

## Key Design Points
- **Rich text editor:** Modern compose experience replacing telnet command-line input. Lower barrier to entry for new players unfamiliar with MUSH conventions
- **Action-attached poses:** Players can embed mechanical actions directly in their writing — flirtation checks, pickpocketing attempts, dice rolls, arm wrestling, throwing objects. Seamlessly integrated into the narrative flow rather than jarring separate commands
- **Scene engagement mechanics:** Reactions/emoticons on poses, liking poses, pose-of-the-scene awards. Younger players used to social media can engage naturally
- **Passive advancement:** Social scenes mechanically advance characters — skill development, relationship building, magical discoveries can all happen during bar scenes and balls
- **Aura farming:** A character's resonance feeds off how they're perceived. Writing a dramatic entrance at a ball literally increases magical power. Making the social game mechanically meaningful
- **Scene modes:** Poses, says, whispers — different communication modes within a scene, including private exchanges
- **Persona/disguise system:** Characters can appear under alternate identities during scenes
- **Scene recording:** All scenes are recorded for continuity, story tracking, and reference
- **Dice rolling integration:** Checks and attempts woven into scene flow without disrupting narrative pacing

## What Exists

### Interaction System — DONE
- **Models:** Interaction (7-column partitioned table: persona, scene, content, mode, visibility, timestamp), InteractionReaction (bridge engagement model — emoji toggle), InteractionFavorite (private bookmarks), InteractionTargetPersona (thread derivation)
- **Identity:** Persona (unified with PersonaType: PRIMARY/ESTABLISHED/TEMPORARY) → CharacterIdentity → Character → RosterEntry. PersonaDiscovery for disguise reveal tracking.
- **Privacy:** 4-tier model (public/private/very_private/ephemeral). Scene privacy_mode sets floor. Very_private blocks staff. Ephemeral never persists.
- **Services:** create_interaction, record_interaction (reads active_persona, resolves audience), record_whisper_interaction, push_interaction (WebSocket delivery), can_view_interaction, mark_very_private, delete_interaction
- **API:** InteractionViewSet, InteractionFavoriteViewSet, InteractionReactionViewSet
- **Performance:** PostgreSQL monthly partitioning (2026-2028), BRIN indexes, UNION subquery visibility filtering
- **Real-time:** push_interaction() sends structured payloads via Evennia WebSocket to connected clients. Frontend receives via INTERACTION message type.

### Communication Flow — DONE
- **Broadcast + Record separation:** message_location() is pure real-time broadcast (no DB writes). record_interaction() handles persistence. Action classes call both explicitly.
- **Action wiring:** PoseAction, SayAction, WhisperAction all call broadcast + record
- **message_location() cleaned:** ~15 lines, no SceneMessage/Persona creation

### SceneMessage — REMOVED
- SceneMessage, SceneMessageSupplementalData, SceneMessageReaction all deleted
- MessageContext, MessageMode constants removed (Interaction uses InteractionMode)
- All viewsets, serializers, permissions, filters, factories, admin, tests removed
- Frontend fully switched to Interaction API + WebSocket

### Places System — DONE (PR #348)
- **Models:** Place (sub-locations within rooms), PlacePresence (who's at which place)
- **Services:** Place management and presence tracking
- **Frontend:** PlaceBar component for sub-location display

### Scene Actions — DONE (PR #348)
- **Models:** SceneActionRequest (consent flow for targeted actions)
- **Services:** Action request creation, consent handling, resolution
- **Actions:** Social actions (flirt, taunt, etc.) in actions/definitions/social.py
- **Frontend:** ActionPanel, ConsentPrompt, PersonaContextMenu components
- **Constants:** SceneActionRequestStatus, SceneActionType

### Multi-Target Action Consent (#572 follow-ups) — DONE (#1177, #1178, #1259)

Two follow-ups from the #572 multi-target dispatch foundation:

- **Per-target resolver invocation (#1178):** `respond_to_action_target()` now fires
  the registered action resolver once per accepted `SceneActionTarget` row, symmetric with
  `respond_to_action_request()`. Resolvers for multi-target actions must keep cast-level
  side-effects idempotent across invocations.
- **Additional-target consent UI (#1177):**
  - `SceneActionTarget` read-only listing endpoint — `GET /api/action-targets/` (filterable
    by `scene` and `status`); registered in scenes URL router as `action-targets`.
  - `SceneActionTargetSerializer` — flat read payload with `action_target_id`,
    `action_request_id`, `target_persona_id`, `initiator_name`, `scene`, `action_key`,
    `technique_name`, `pose_text`, `strain_commitment`, `status`, `created_at`.
  - `SceneActionTargetFilter` — `scene` + `status` django-filter FilterSet.
  - Frontend `ConsentPrompt` extended: polls `GET /api/action-targets/?scene={id}&status=pending`
    every 5 s alongside the primary-request queue; renders amber consent cards for pending
    additional-target rows; Accept/Deny dispatches to
    `POST /api/action-requests/{id}/respond/` with `target_persona_id`.
- **Additional-target combat-risk parity (#1259):** `SceneActionTargetSerializer` now
  includes `combat_risk_level` (computed from the row's own target persona). `ConsentPrompt`
  renders the combat-risk warning on additional-target cards, matching primary-target behaviour.

### Effort/Difficulty Split + Defender Agency + Good-Sport Kudos — DONE (#1275)

A deliberate extension of the consent flow replacing the prior "uniform cast-level difficulty"
model with a split where the initiator controls effort and each defender controls difficulty:

- **Initiator declares effort** at dispatch via `SceneActionRequest.effort_level` (EffortLevel).
  `EFFORT_CHECK_MODIFIER[effort_level]` is added to the check pool at resolution and the
  initiator is charged social fatigue proportional to effort.
- **Abstract base `DefenderConsentFields`** (`action_models.py`) — inherited by both
  `SceneActionRequest` (primary target) and `SceneActionTarget` (additional targets). Carries:
  `difficulty_choice` (DifficultyChoice plausibility band, default NORMAL), `resolved_difficulty`,
  `resist_effort_level` (EffortLevel, optional active resistance).
- **Plausibility bands** in `ConsentCard` (frontend): "It works" → EASY, "Hard but possible" →
  HARD, "No way" → DAUNTING (accept-but-daunting, not a deny). The initiator's dispatch UI
  has an effort picker.
- **Active resistance (Slice C):** when the defender selects "Dig in (costs stamina)", a
  `resist_effort_level` is stored at consent. `compute_resist_increment(defender, resist_effort)`
  in `world.checks.services` resolves the `Composure` CheckType (willpower-weighted, seeded by
  `create_resistance_check_types()` in `world.checks.factories`) and produces a numeric increment
  added to the plausibility base. The defender is charged `RESIST_FATIGUE_BASE` (currently 1)
  social fatigue.
- **Good-sport kudos (Slice B):** `KudosDifficultyWeight` (staff-tunable band→multiplier,
  one row per DifficultyChoice) and `WeeklySocialEngagement` + `WeeklyEngagementInitiator`
  ledger. On ACCEPT, `_accrue_engagement_for_persona` in `action_services.py` calls
  `progression.services.engagement.accrue()` with `default_amount × weight_for(band)` for the
  defender's account. Anti-farm guards: NPC defender/initiator and self-targeting are skipped.
  At weekly rollover `grant_social_engagement_kudos()` grants Kudos to all ledgers meeting
  `MIN_ENGAGEMENT_BAR` distinct initiators (currently 2).
- **NPC/area fallback:** `difficulty_choice` defaults to its authored value when there is no
  consenting player; area actions use their own `difficulty_choice`.
- **Consent serializer:** `ConsentResponseSerializer` accepts `difficulty` (DifficultyChoice)
  and `resist_effort` (EffortLevel) in `POST /api/action-requests/{id}/respond/`.
- **Slice D deferred → #520:** effort↔strain unification + scene-seriousness gating remain
  out of scope and are tracked in the non-combat rounds epic.

### Scene System (core)
- **Models:** Scene (privacy_mode, summary fields), SceneParticipation, SceneSummaryRevision
- **APIs:** SceneViewSet, PersonaViewSet, SceneSummaryRevisionViewSet, PlaceViewSet, SceneActionRequestViewSet, SceneActionTargetViewSet
- **Frontend:** Scene list/detail pages, interaction feed, action panel

### Three-Mode Round Framework + Scene-Adaptive Cast — DONE (#1351)

Non-combat scene rounds (`SceneRound`) now support three action-gating modes:

- **OPEN** — every action resolves immediately, no quota.
- **POSE_ORDER** — default for social rounds; actions resolve immediately and `round_number` advances
  once `ceil(advance_quorum_pct × active_count)` distinct participants have acted this round.
- **STRICT** — actions are declared into a ledger while `is_declaration_open`; the round resolves as a
  batch when presence-gated completion is met or a GM force-resolves.

`SceneRoundDefaultsConfig` (singleton pk=1) lets staff tune `default_mode`, `advance_quorum_pct`,
`max_actions_per_round`, `per_target_repeat_lock`, and `anti_spam_seconds` without a code deploy.
`SceneActionDeclaration` is a multi-action-per-round ledger (`is_immediate` + `target_persona` FK).

`ActionBackend.SCENE_ADAPTIVE` (`actions/player_interface.py`) is the fourth dispatch backend for
actions that work inside and outside combat: anti-spam floor → `round_declaration` hook (declares
into a combat round when in one, else resolves immediately) → `is_repeat_blocked` check →
immediate execution with pose-order ledger side-effects.

`CastTechniqueAction` (key `"cast_technique"`, `actions/definitions/cast.py`) implements the unified
technique cast. The unified `cast` command (`CmdDeclareTechnique`, `commands/combat.py`) replaces
the deleted `CmdAttempt`; parses `cast <technique> [at <target>] [effort=<level>]`.

### Scene Administration Command + Per-Scene Round-Mode Control — DONE (#1445)

GM and co-owner tooling for scene lifecycle and round-mode adjustment, delivered as the
`scene` command (`CmdScene`, `commands/scene.py`) and three Actions.

**What shipped:**

- **Co-ownership model:** all characters present at scene creation become co-owners
  (`is_owner=True` on `SceneParticipation`); latecomers are non-owner participants
  (anti-grab).
- **`is_story_runner` property** on `Character` (`typeclasses/characters.py`):
  `False` on base characters; `True` on `GMCharacter` / `StaffCharacter`
  (`typeclasses/gm_characters.py`).
- **Permission helper** `actor_can_administer_scene(actor, scene)` (`scene_admin_services.py`):
  grants GM/Staff characters unconditional access; staff accounts and co-owners follow.
- **Service functions** (`scene_admin_services.py`): `resolve_actor_account`,
  `add_present_as_co_owners`, `finish_scene_full` (extracted from the viewset).
- **`set_scene_round_mode`** (`round_services.py`) + `RoundModeError`: applies mode/knob
  changes in-place; guards against STRICT-exit with pending deferred declarations (#1466
  removed the DANGER-immutable guard — danger rounds are ordinary STRICT rounds).
- **Actions:** `StartSceneAction` (key `"start_scene"`), `FinishSceneAction`
  (key `"finish_scene"`) in `actions/definitions/scenes.py`; `SetRoundModeAction`
  (key `"set_round_mode"`) in `actions/definitions/rounds.py`.
  `StartRoundAction` extended: knob overrides at round creation require scene admin.
- **Telnet:** `CmdScene` (`scene`) with subcommands `start [name]` / `finish` /
  `round [open|pose_order|strict] [quorum=<pct>] [cap=<n>] [lock=on/off]` / `status`.
- **Web:** `POST /api/scenes/{id}/set-round-mode/` (gated `IsSceneGMOrOwnerOrStaff`,
  dispatches `SetRoundModeAction`).

**DANGER → STRICT unification — DONE (#1466):** danger is no longer a separate round type;
an acute peril ensures an ordinary STRICT `SceneRound(start_reason=DANGER)` that ticks the
peril at presence-gated resolution and auto-ends when it clears.

**GM enrollment for ordinary GM-run scenes — DONE (#2113):** `SceneParticipation.is_gm` — the
predicate every GM-combat surface gates on — had only one production writer, the crossover
Lead-GM path; an ordinary trust-tier GM running their own table's session never got flagged.
Two writers now cover it: `enroll_present_table_gms(scene, room)` (`scene_admin_services.py`)
auto-flags a present account that owns an ACTIVE `GMTable` with an *other* present character
holding an active `GMTableMembership` on it, called from `StartSceneAction.execute()` on both
the new-scene and mid-scene-join paths; `GrantSceneGMAction` (`scene gm <name>`, key
`"grant_scene_gm"`) is the explicit fallback for cases auto-detection can't reach, gated on
`actor_can_administer_scene` plus the target holding a `GMProfile`.

### Web Round-Mode Control — DONE (#1467, parity for #1445)

Frontend parity for `scene round` (telnet):

- **`active_round` read field** on `SceneDetailSerializer` — `SceneRoundSerializer` (read-only)
  nested under the scene detail. Fields: `mode`, `advance_quorum_pct`, `max_actions_per_round`,
  `per_target_repeat_lock`, `status`, `round_number`, `is_danger`. `null` when no active round.
- **`active_round_for_room(room) -> SceneRound | None`** promoted to a public service in
  `round_services.py` (was a private action helper); consumed by `SceneDetailSerializer.get_active_round`.
- **`RoundSettingsDialog`** (`frontend/src/scenes/components/RoundSettingsDialog.tsx`) — GM/owner/
  staff-gated React dialog; reads `active_round` from the scene detail and dispatches
  `useSetRoundMode` → `POST /api/scenes/{id}/set-round-mode/`. Wired into `SceneHeader.tsx`.

**Web danger lock reconciled — DONE (#1476):** `RoundSettingsDialog` no longer locks
danger rounds. Since #1466 a danger round is an ordinary STRICT round, so the dialog lets
a scene admin reconfigure a live danger round's knobs/mode like any other round (web/telnet
parity, #1328). `is_danger` now only drives a non-blocking informational note.

**Details:** [scenes.md](../systems/scenes.md) §"Scene Administration (#1445)"

### Persona Telnet Switch + Shared set-active Path — DONE (#1347)

Web/telnet parity for active-persona management. Before this, `PersonaViewSet.set_active`
called `set_active_persona` directly (bypassing `action.run()`); telnet had no way to switch.

- **`SetActivePersonaAction`** (key `"set_active_persona"`, REGISTRY, `target_type=SELF`,
  kwarg `persona_id`) in `actions/definitions/personas.py` — validates persona ownership,
  wraps `world.scenes.services.set_active_persona` (still the sole mutator).
- **`PersonaViewSet.set_active`** now routes through `dispatch_player_action` → the action
  instead of calling the service directly. API request/response unchanged.
- **`CmdPersona`** (`persona`, alias `wear-face`) in `commands/persona.py` — thin
  `DispatchCommand`; bare `persona`/`persona list` renders the caller's faces (active marked
  `◄ active`); `persona <name>` or `wear-face <name>` dispatches the action.
- **E2E:** `src/integration_tests/pipeline/test_persona_telnet_e2e.py` (telnet list/switch,
  web/telnet parity, negative cases).
- **Scope boundary:** pose/sdesc reflection of the presented persona remains **#1109**.

**Details:** [appearance_and_identity.md](../systems/appearance_and_identity.md) §"Layer 1 — Persona"

### PC-to-PC Identification Loop — DONE (#1107 slice 5, Apostate's 2026-07-03 ruling)

The mask fiction's missing other half: a viewer can now *try to find out* who's
really under a masked/disguised character, instead of a mask being an unbreakable
lock.

- **Seed:** a dedicated **Identification** `CheckType` (intellect + Investigation) —
  `ensure_identification_check` in `world/seeds/investigation_checks.py`, distinct
  from `Search` (perception + Investigation).
- **Service (`world/forms/services/identification.py`):**
  `identification_difficulty(viewer_sheet, target_character)` — baseline from the
  target's active fake overlay (`DisguiseKind` × `ConcealmentLevel`) or the bare
  "mask floor" for a name-only fake persona with no overlay, eased by an active
  `CharacterRelationship` and the target's true-persona `fame_tier` (both stack —
  PLACEHOLDER additive combine rule, contrast `social_difficulty.py`'s `max()`
  precedent). `attempt_identification(viewer, target, guess_name=None)` rolls
  `perform_check` against that difficulty (a correct named guess eases it, but never
  rescues the auto-fail band), writes a `PersonaDiscovery` row on success via the
  same writer the GM `PERSONA_LINK` clue uses (#2120 — second in-game producer), and
  fake-IDs a random active `Functionary` (new `random_active_functionary()` picker,
  `world/npc_services/functionaries.py`) on a botch — **never a real PC**. Failure
  and auto-fail share the identical player-facing message (the oracle rule).
- **Action + telnet + web:** `IdentifyAction` (registry key `identify`,
  `actions/definitions/identification.py`) — a plain registry action (not
  `ActionTemplate`-backed, unlike Deceive/Persuade), since identify's bespoke
  check pipeline and roller-only messaging don't fit the consequence-pool template
  shape. Telnet `CmdIdentify` (`identify <target>[=<guess>]`,
  `commands/identification.py`). Web reachability is a dedicated "Identify" item on
  `PersonaContextMenu.tsx` dispatching REGISTRY REST directly
  (`useDispatchPlayerAction`) — deliberately **not** listed by
  `get_player_actions`/`ActionPanel.tsx`, since every generic-panel consumer
  dispatches through the CONSENT pipeline (`createActionRequest`), which a
  no-consent private perception roll (ADR-0024) must never enter.
- **Follow-up:** crafted disguise kits (kit quality as a pierce-resistance modifier
  on the baseline) are DEFERRED per the ruling — draft child-issue body at
  `.superpowers/sdd/disguise-kit-issue-draft.md` (not yet filed).

**Details:** [appearance_and_identity.md](../systems/appearance_and_identity.md) §"Identification loop (slice 5)"

### Positioning in Scenes — DONE (#1017, spatial map #2006)
- **Scene API extension:** `SceneDetailSerializer` exposes `positions`, `position_adjacency`, `persona_positions`, and (#2006) `position_nodes`/`position_edges` — the full tactical-map graph — for the scene's room.
- **Frontend:** `SceneTacticalMap` component (`frontend/src/scenes/components/`) renders the position graph as a spatial `@xyflow/react` map — occupant avatars per node, edges styled by passability/gating, click-to-move, and a staff "Set the stage" control — replacing the earlier `RoomPositionsPanel` text-list UI (#2006). `MovementActions` extracted as a shared component (`frontend/src/combat/components/`).
- **Blueprint authoring + staging:** see `docs/roadmap/combat.md` (Positioning — Blueprints + Non-Combat Scene UI section) and `docs/systems/areas.md`.

### Technique-Driven Combat Entrance + Dramatic Moment Suggestion — DONE (#2183, ADR-0113)

A "make an entrance" backed by a technique cast resolves through **one roll**, not two: the
technique's own success level substitutes for the entrance's social check entirely and drives
every downstream consequence via a deferral matrix (inline / hostile-seeded-into-combat /
PENDING-consent / soulfray-gated), so nothing is lost when the real success level isn't known
until later (a declared cast resolving at combat round resolution, or a consent-gated request
resolving on accept).

- **`EntranceAction._execute_technique_entrance`** (`actions/definitions/social.py`) — the
  `enter <technique>[=<target>]` telnet grammar (`CmdEnter`) and the web
  `EntranceTechniqueAttachment` popover both converge here. `SceneActionRequestViewSet
  ._create_technique_entrance` (`world/scenes/action_views.py`, #2183 Task 8 fold-in)
  dispatches the same seam for the REST caller rather than the unrelated technique-as-
  `ActionEnhancement` consent path the rest of that endpoint uses.
- **Recognition bridge:** a qualifying cast never auto-tags — it creates a
  `DramaticMomentSuggestion` (PENDING) a GM later confirms (mints a real
  `DramaticMomentTag`, full resonance + renown award) or dismisses, gated on
  `DramaticMomentType.suggest_on_technique_entrance` / `.suggestion_min_success_level`.
  Web: `DramaticMomentSuggestionViewSet`. Telnet: `CmdMoment`. Frontend:
  `DramaticMomentSuggestionChip` in `PoseUnit`.
- **Combat integration:** `CombatRoundAction.from_entrance` marks a hostile entrance-seeded
  declaration so the suggestion fires at round resolution once the real success level is
  known; a benign entrance cast landing on an embattled ally seats the caster into the fight
  via `seed_or_feed_encounter_from_benign_intervention` — see
  [combat.md](combat.md) "What's PROVEN".
- **Details:** [magic.md](../systems/magic.md#technique-entrance-2183) · ADR:
  [0113](../adr/0113-entrance-carries-the-cast.md).

### Relationship Integration
- RelationshipUpdate has linked_interaction FK and reference_mode

### Design Docs
- `docs/plans/2026-03-19-rp-interactions-privacy-design.md`
- `docs/plans/2026-03-20-identity-hierarchy-persona-refactor-design.md`
- `docs/plans/2026-03-21-character-identity-interaction-wiring-design.md`
- `docs/plans/2026-03-22-persona-simplification-design.md`
- `docs/plans/2026-03-23-scenemessage-deprecation-design.md`

## What's Needed for MVP

### Frontend UX (highest priority)

> **Status correction (2026-07-10 audit, epic #2155) — RESOLVED (#2156):** the
> two-surface split flagged by the audit (built-on-`/scenes/:id`-only, absent from
> `/game`) is closed. `GamePage` is now the composition root: it derives the active
> session's scene, composes `useSceneInteractions` + `useThreading` once, and feeds
> the result to `ConversationSidebar` (thread sidebar, unread badges, filter modal),
> the center feed (chat-bubble `PoseUnit`s + `SystemLane`), and the scene toolset
> (actions/places/consent/composer modes incl. tabletalk) — all on `/game`.
> `/scenes/:id` remains the unchanged record/detail page (`SceneInteractionPanel`).
> What was built: one-play-surface composition on `/game`; per-thread unread
> backed by session last-seen (with a scene-load baseline scalar so mid-session
> new threads badge correctly); `PoseUnit` restyled as avatar-bubble chat cards
> (author, timestamp, prose, reactions — no monospace/terminal styling) with
> avatar-click opening a `CharacterCardDrawer` in place (Friend/Whisper actions);
> `viewer_is_present` on `PlaceSerializer`; pose co-location validation
> (`submit-pose` rejects a pose into a located scene the actor isn't physically
> in); and the `/game` places query fixed to key off the scene's room id rather
> than the scene id. See `docs/systems/scenes.md` for the UI composition detail
> and ADR-0111.
>
> The scene feed markdown gap the audit also flagged (`EvenniaMessage` never
> parsing `RichTextInput`'s markdown) is closed by the same restyle: the
> structured feed renders `FormattedContent`, not raw `EvenniaMessage`.

- **Rich text editor** — DONE. `RichTextInput` (toolbar, shortcuts, color picker,
  `@name` autocomplete) composes into scenes on `/game`; the feed renders it via
  `FormattedContent`, not the legacy raw `EvenniaMessage` log
- **Smart input composer** — DONE. `ModeSelector` (pose/say/emit/whisper/tabletalk)
  plus action attachment mount on `/game`'s composer, wired to the same
  `useSceneInteractions` session the feed and toolset share; tabletalk is live
  (no longer hardcoded off)
- **Conversation threading** — DONE. `useThreading`/`ThreadSidebar`/`ThreadFilterModal`
  (grouping by whisper-set/place/target) render on `/game` via `ConversationSidebar`;
  per-thread unread counts are backed by session last-seen, not stubbed to 0
- **~~Scene scheduling and discovery~~** — Split into separate concerns:
  - **Events system** (`world/events`) — scheduled RP gatherings with calendar, invitations, room modifications. See [Events roadmap](events.md) and `docs/plans/2026-03-27-events-system-design.md`
  - **Grid presence** — "who's where" on public rooms for organic RP, future graphical map. Separate feature, not part of scenes or events

### Character Setup
- **Persona auto-creation** — Part of broader CG finalization process. When a character finishes creation and enters the game: CharacterIdentity + primary Persona created, starting location assigned, society memberships initialized. See `memory/project_cg_finalization_needs.md`

### Engagement System
- **Kudos/voting/favorites** — InteractionReaction is fully integrated (model, API, frontend, admin, tests) and works well as-is. The future engagement system should design a migration path from InteractionReaction when specced, including data migration, API versioning, and partition SQL updates. Not a pre-emptive refactor
- **Scene-based XP rewards** — Earning XP for participation and quality

### Mechanical Integration
- **Aura farming** — Scene perception feeds into resonance. Dramatic moments literally increase magical power
- **Passive advancement** — Scene participation mechanically advances characters: skill development, relationship building. Certain check types award development points and prevent rust

### Ephemeral Scenes
- **Real-time delivery without persistence** — For ephemeral scenes, push_interaction already handles WebSocket delivery. Need to ensure create_interaction returns None (already does) and push_interaction still sends the payload. May need a separate code path that pushes without persisting.

## Notes
