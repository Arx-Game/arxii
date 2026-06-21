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
  `resist_effort_level` (EffortLevel, optional active resistance), `engagement_credited`.
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

### Positioning in Scenes — DONE (#1017)
- **Scene API extension:** `SceneDetailSerializer` exposes `positions`, `position_adjacency`, `persona_positions` for the scene's room.
- **Frontend:** `RoomPositionsPanel` component (`frontend/src/scenes/components/`) renders positions, persona placement, move action, and a staff "Set the stage" control. `MovementActions` extracted as a shared component (`frontend/src/combat/components/`).
- **Blueprint authoring + staging:** see `docs/roadmap/combat.md` (Positioning — Blueprints + Non-Combat Scene UI section) and `docs/systems/areas.md`.

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
- **Rich text editor** — Modern compose experience with Discord/F-list-style formatting (bold, italic, links, maybe character mentions). Lower barrier for new players. Should feel like a modern chat room, not a text terminal
- **Smart input composer** — MMO-style mode selector to the left of the chat input. Controls command (pose/emit), target (room/group/individual), with color coding. Defaults to the last conversational thread. Discreetly shows audience scope
- **Conversation threading** — Frontend derives threads from target patterns in the interaction stream. Collapsible, expandable, filterable. In a room with 30 people, follow just the threads you care about
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
