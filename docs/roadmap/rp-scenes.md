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

### Scene System (core)
- **Models:** Scene (privacy_mode, summary fields), SceneParticipation, SceneSummaryRevision
- **APIs:** SceneViewSet, PersonaViewSet, SceneSummaryRevisionViewSet, PlaceViewSet, SceneActionRequestViewSet
- **Frontend:** Scene list/detail pages, interaction feed, action panel

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
