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

### Interaction System (new)
- **Models:** Interaction (7-column partitioned table: persona, scene, content, mode, visibility, timestamp), InteractionAudience (guise-based viewer tracking), InteractionFavorite (private bookmarks), InteractionTargetPersona (thread derivation), SceneSummaryRevision (ephemeral scene summaries)
- **Identity hierarchy:** Persona (point-in-time appearance) → Guise (persistent identity) → Character → RosterEntry. PersonaIdentification tracks disguise reveals per character.
- **Privacy:** 4-tier model (public/private/very_private/ephemeral). Scene privacy_mode sets floor. Interaction visibility can only escalate. Very_private blocks staff. Ephemeral never persists.
- **Services:** create_interaction, can_view_interaction, mark_very_private, delete_interaction (30-day hard delete)
- **API:** InteractionViewSet (read + delete + mark_private), InteractionFavoriteViewSet, SceneSummaryRevisionViewSet, UNION subquery privacy filtering
- **Performance:** PostgreSQL monthly partitioning (2026-2028), BRIN indexes, composite FKs, partial indexes on very_private and scene IS NULL
- **Relationship integration:** RelationshipUpdate has linked_interaction FK and reference_mode (all_weekly/specific_interaction/specific_scene)
- **Design docs:** `docs/plans/2026-03-19-rp-interactions-privacy-design.md`, `docs/plans/2026-03-20-identity-hierarchy-persona-refactor-design.md`

### Scene System (existing)
- **Models:** Scene (with privacy_mode: public/private/ephemeral, summary fields), SceneParticipation, Persona (now with guise FK, nullable participation), SceneMessage (legacy — to be replaced by Interaction), SceneMessageReaction
- **APIs:** Full viewsets for scenes, messages, participation, personas
- **Frontend:** Scene components and pages in frontend/src/scenes/
- **Commands:** Pose/say/whisper commands via Evennia actions
- **Tests:** 120 scene tests, 76 relationship tests

## What's Needed for MVP

### Integration (highest priority)
- **Communication flow wiring** — Connect pose/emit/say/whisper commands to create Interaction records instead of (or alongside) SceneMessages. The `message_location()` flow service function is the primary integration point
- **Persona auto-creation** — Service for auto-creating default personas from guises when characters interact. Currently `message_location()` creates personas but needs full guise-backed auto-creation for all interaction paths
- **SceneMessage deprecation** — Once Interactions are the universal record, SceneMessage becomes redundant. Scene detail views should query Interactions filtered by scene FK. Migration plan for existing frontend components
- **Action-type interactions** — Support for mechanical actions coupled with text (flirt, seduce, taunt, pickpocket, cast spell). The Interaction model's `mode=ACTION` covers this, but the creation flow needs to accept check results and attach them to interactions

### Frontend UX
- **Smart input composer** — MMO-style mode selector to the left of the chat input. Controls command (pose/emit), target (room/group/individual), with color coding. Defaults to the last conversational thread. Discreetly shows audience scope
- **Rich text editor** — Modern compose experience replacing plain text input. Lower barrier for new players
- **Conversation threading** — Frontend derives threads from target patterns in the interaction stream. Collapsible, expandable, filterable. In a room with 30 people, follow just the threads you care about
- **Scene scheduling and discovery** — Finding active scenes, joining easily

### Mechanical Integration
- **Check integration in interactions** — Embed mechanical checks directly into the writing flow. Player selects an action (flirt, taunt, etc.), writes their pose, and the check happens as part of the interaction. No separate command needed
- **Social check consent flow** — Target player sets difficulty (reject/hard/even/easy). Allowing a roll potentially awards kudos. The flow for social checks where the receiving player decides how their character responds
- **Pose reactions and engagement** — Likes, emoticons, pose-of-the-scene awards. Social feedback tied to the kudos system
- **Aura farming** — Scene perception feeds into resonance. Dramatic moments literally increase magical power
- **Passive advancement** — Scene participation mechanically advances characters: skill development, relationship building. Certain check types award development points and prevent rust
- **Scene-based XP rewards** — Earning XP for participation and quality

### Ephemeral Scenes
- **Real-time delivery without persistence** — Technical approach for ephemeral scene interactions. May bypass the ORM entirely and deliver via WebSocket/Evennia msg() only. Content never touches the database

## Notes
