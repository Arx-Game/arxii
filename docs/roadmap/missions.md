# Missions & Living Grid

**Status:** not-started
**Depends on:** Checks, Mechanics (Challenges/Situations), Conditions, Areas, Instances, Traits, Skills, Distinctions, Societies

## Overview
Missions are branching narrative quest chains — the primary way characters interact with the living world. Think Crusader Kings event chains: a character receives a mission with broad objectives, makes decisions at branching points gated by different skills and traits, and the consequences reshape the world around them.

## Key Design Points
- **Mission sources:** Guild/quest-giver NPCs, found objects on grid, encountering ongoing situations in public rooms
- **Branching decision trees:** Each decision point offers multiple approaches appealing to different character builds. A high-charm character might seduce their way past a guard; a stealthy one picks the lock. Distinctions and unique traits unlock special options. Decision points map to **Applications** (Capability + Property = eligibility) which the system uses to generate available approaches automatically
- **Challenge resolution at decision points:** Uses the Challenges/Situations system in the mechanics app. Each decision point is a Challenge with Properties; the system matches character Capabilities via Applications to surface available approaches
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
- **Checks:** Full check resolution pipeline with trait-to-rank conversion, result charts
- **Challenges/Situations (mechanics app):** ChallengeTemplate, ChallengeInstance, SituationTemplate, SituationInstance, ChallengeApproach — atomic problems with Properties, severity, resolution types, and approach matching via Applications. Situations compose Challenges with dependencies and narrative framing. Mission stages will map directly to SituationInstances
- **Properties & Applications (mechanics app):** PropertyCategory, Property, Application — the eligibility layer that connects character Capabilities to Challenge approaches. The system auto-generates available actions based on what a character can do vs. what a Challenge requires
- **Capability sources:** TechniqueCapabilityGrant (magic), TraitCapabilityDerivation (mechanics), ConditionTemplate capabilities (conditions) — multiple sources feed into the action generation pipeline
- **Conditions:** Persistent state tracking with stage progression, now with Properties M2M for integration with the Challenge system
- **No mission-specific models exist** — but the Challenge/Situation infrastructure provides the foundation for mission stages

## What's Needed for MVP
- Mission model — definition, metadata, rewards; stages map to SituationTemplates
- Mission instance tracking — active missions per character, progress, decisions made; stage instances map to SituationInstances
- Decision tree composition — branching points use SituationChallengeLinks with dependencies; gating uses Applications and prerequisite keys
- NPC generation for missions — random targets, quest givers, complications
- World consequence system — how mission outcomes affect grid state, society territory, alerts
- Mission reward distribution — legend, reputation, XP, items, codex entries
- Mission discovery — how characters find/receive missions (quest givers, found objects, grid events)
- Shared mission support — multiple players on the same mission instance
- Player retelling system — writing summaries for bonus legend
- Mission UI — web interface for tracking active missions, making decisions, viewing outcomes

## Notes
