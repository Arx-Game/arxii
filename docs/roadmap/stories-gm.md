# Stories & GM Tables

**Status:** in-progress
**Depends on:** Scenes, Missions, Codex, Relationships, Progression

## Overview
The narrative engine that tracks every character's story arc from CG backstory through every plot beat to retirement or death. GMs manage "tables" of PCs, overseeing their stories and running adventures. GM trust levels determine the scale of impact they can have on the shared world.

## Key Design Points
- **Full arc tracking:** A character's story is traced from CG backstory design through every major plot point. Past entries reference scenes, include player and GM notes, show PC reactions, and track relationship impacts
- **Story beats and steps:** Stories have structured steps summarizing what happened, with links to referenced scenes and mechanical tasks (research needed, enemies to defeat, dungeons to explore, missions to complete)
- **GM Tables:** Virtual tabletop structure. Each GM manages a slice of the world for their assigned PCs. GMs help keep track of PC stories, run adventures, maintain continuity
- **GM progression:** GMs level up through trust ratings, staff promotion, and player feedback. Newbie GMs run low-stakes non-lethal adventures. Higher-tier GMs can run world-changing stories that permanently reshape the setting
- **Task modes:** Story steps can be: missions (solo/async via mission system), research projects (offscreen cron-based rolls), or GM-scheduled sessions
- **Time reconciliation:** Three time modes coexist — canon world time (3:1 game-to-real ratio with character aging), scene time (slow RP pace where 10 minutes IC spans hours of typing), and abstract GM session time (pinned to a specific narrative moment)
- **Coordinated world:** One staffer coordinates all GMs so the game maintains a single connected continuity. Every GM's stories happen in the same world, and actions in one table can affect others
- **Player agency:** Players can reference active stories, see story beats, track what's happening, and have mechanical tasks they can pursue independently between GM sessions

## What Exists
- **Models:** Story (campaign container with trust requirements), Chapter (major arcs with ordering), Episode (individual sessions linking to scenes), EpisodeScene (bridge table), StoryParticipation (character involvement), TrustCategory, PlayerTrust, PlayerTrustLevel, StoryTrustRequirement (trust system), StoryFeedback, TrustCategoryFeedbackRating (feedback for trust building)
- **APIs:** Full viewsets and serializers
- **Tests:** Model tests, view permission tests

## What's Needed for MVP
- GM Table model — the container linking a GM to their group of PCs and active stories
- Story beat / step tracking — structured steps with mechanical tasks, scene references, notes
- Player story view — seeing your active stories, past entries, what's needed next
- GM dashboard — managing assigned PCs, their stories, scheduling sessions
- Task mode integration — connecting story steps to missions (async), research (cron), and GM sessions (scheduled)
- Time mode handling — reconciling canon time, scene time, and session time
- GM level system implementation — scaling abilities, reward caps, and impact scope by GM trust level
- Story scheduling — coordinating GM availability with player availability
- World impact tracking — how GM story outcomes affect the broader world state
- Cross-table coordination tools — staff view of all active stories and their world impacts
- Story UI — web interface for players and GMs to interact with the story system

## Notes
