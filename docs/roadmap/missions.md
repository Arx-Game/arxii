# Missions & Living Grid

**Status:** not-started
**Depends on:** Checks, Attempts, Conditions, Areas, Instances, Traits, Skills, Distinctions, Societies

## Overview
Missions are branching narrative quest chains — the primary way characters interact with the living world. Think Crusader Kings event chains: a character receives a mission with broad objectives, makes decisions at branching points gated by different skills and traits, and the consequences reshape the world around them.

## Key Design Points
- **Mission sources:** Guild/quest-giver NPCs, found objects on grid, encountering ongoing situations in public rooms
- **Branching decision trees:** Each decision point offers multiple approaches appealing to different character builds. A high-charm character might seduce their way past a guard; a stealthy one picks the lock. Distinctions and unique traits unlock special options
- **Skill checks at decision points:** Uses the existing check/attempt system for resolution
- **Instanced moments:** Missions can spin up private instances (e.g., luring an NPC to a private room) using the instances system
- **World consequences:** Mission outcomes ripple outward — a city goes on high alert, a character becomes wanted, crime gangs gain territory, a war front shifts
- **Player retelling:** The system provides facts and outcomes; players write the dramatic retelling for bonus legend. Encourages creative expression
- **Designed for solo AND small groups:** While the Living Grid allows solo play, missions are enhanced with other players. Shared missions let groups experience things together and build relationships
- **Randomly generated elements:** NPC targets, locations, complications — keeps missions feeling fresh
- **Legend and reputation:** Dangerous missions grant legend. Mission outcomes feed into society reputation
- **NOT using the Flows system:** Individual mission logic rather than the abstracted Flows engine — missions need specific, tailored behavior

## What Exists
- **Areas app:** 9-level spatial hierarchy with materialized views for efficient path queries
- **Instances app:** Temporary instanced room lifecycle management with scene preservation
- **Checks/Attempts:** Full check resolution pipeline with trait-to-rank conversion, result charts, and narrative consequence roulette display
- **Conditions:** Persistent state tracking with stage progression
- **No mission-specific models exist**

## What's Needed for MVP
- Mission model — definition, stages, branching logic, requirements, rewards
- Mission instance tracking — active missions per character, progress, decisions made
- Decision tree engine — branching points with skill/trait/distinction gating
- NPC generation for missions — random targets, quest givers, complications
- World consequence system — how mission outcomes affect grid state, society territory, alerts
- Mission reward distribution — legend, reputation, XP, items, codex entries
- Mission discovery — how characters find/receive missions (quest givers, found objects, grid events)
- Shared mission support — multiple players on the same mission instance
- Player retelling system — writing summaries for bonus legend
- Mission UI — web interface for tracking active missions, making decisions, viewing outcomes

## Notes
