# Codex & Knowledge

**Status:** in-progress
**Depends on:** Scenes, Relationships (for sharing), Missions (for discovery), Stories

## Overview
The living lore repository that reflects what each character knows — not a static wiki, but an active gameplay system. Players discover secrets through missions, NPC relationships, research projects, and adventuring, then choose what to share or withhold. The biggest story arcs have layers of mystery that reward investigation.

## Key Design Points
- **Character-scoped knowledge:** The codex shows what YOUR character knows, with hints about what might be missing. Not everyone sees the same information
- **Discovery through gameplay:** NPC relationships, research projects, missions, environmental puzzles, and social scenes all feed codex entries. A spy charming NPCs discovers secrets; an adventuring party researching in the Great Archive pieces together clues
- **Multi-step discovery chains:** A mysterious obelisk in a dead language might take several missions to decode, each step unlocking new missions related to the underlying story
- **Knowledge as currency:** Players choose to share or withhold secrets. Sharing builds relationships and reputation; withholding preserves strategic advantage
- **Research mechanics:** Offscreen collaborative research projects where characters roll against relevant skills over time (cron-based)
- **Teaching system:** Characters can teach codex knowledge to others, with AP costs and gold costs
- **CG knowledge grants:** Characters start with knowledge based on their origin, path, distinctions, and tradition
- **Mystery-driven arcs:** The biggest world stories have hidden truths that players are highly motivated to uncover

## What Exists
- **Models:** CodexCategory, CodexSubject (nestable with breadcrumb paths), CodexSubjectBreadcrumb (materialized view), CodexEntry (lore pieces with prerequisites, learn/share costs, visibility), CharacterCodexKnowledge (learning progress — uncovered/known), CodexClue (hints granting research progress), CharacterClueKnowledge, CodexTeachingOffer (teaching with AP banking), BeginningsCodexGrant, PathCodexGrant, DistinctionCodexGrant, TraditionCodexGrant (CG knowledge grants)
- **APIs:** Full viewsets and serializers
- **Frontend:** Codex pages, components, and queries in frontend/src/codex/. IC/OOC split navigation, breadcrumb display
- **Tests:** Model tests, visibility tests, view tests

## What's Needed for MVP
- Research project system — offscreen collaborative research with skill rolls over time
- Discovery triggers — connecting missions, NPC interactions, and environmental puzzles to codex unlocks
- Knowledge sharing UI — player-facing interface for choosing what to share with whom
- Multi-step discovery chains — linking codex entries to mission unlocks and story progression
- Clue integration with missions — finding clues during missions that advance codex knowledge
- NPC relationship discovery — spy/charm mechanics that reveal hidden codex entries
- Research UI — initiating, tracking, and completing research projects
- Lore content — hundreds of codex entries need to be authored for the game world

## Notes
