# Capabilities, Applications & Challenges

**Status:** in-progress
**Depends on:** Traits, Conditions, Magic, Mechanics (modifiers)

## Overview
The foundational interaction model for Arx II. This system defines how characters interact with the game world through four layers: what things ARE (Properties), what characters CAN DO (Capabilities), WHERE those capabilities are relevant (Applications), and what becomes AVAILABLE in context (Actions). Every system that involves characters interacting with obstacles, creatures, environments, or each other follows this pattern.

The architecture doc lives at `docs/architecture/property-capability-action.md`.

## How It Works

1. **GMs and designers tag things with Properties** — a door is "wooden" and "locked", a creature is "abyssal" and "armored", a room is "dark"
2. **Characters have Capabilities** from multiple sources — Techniques grant fire_generation, high Strength grants force, an active condition grants flight
3. **Applications declare eligibility** — "fire_generation + flammable = Burn Through" means any character with fire_generation can attempt to burn flammable things
4. **The system generates Actions** — when a character enters a room with a locked wooden door, the system checks their Capabilities against the door's Properties and surfaces what they can do: pick the lock (lockpicking + locked), burn through (fire_generation + flammable), force open (force + breakable)

Challenges are the atomic problems characters face. Situations compose Challenges into narrative sequences with dependencies (e.g., "defeat the guards, THEN breach the gate, THEN confront the boss").

## What Exists

### Data Models (mechanics app)
- **PropertyCategory, Property** — tagged descriptors for anything in the game world
- **Application** — links a CapabilityType to a target Property with optional required_effect_property
- **TraitCapabilityDerivation** — maps Traits to Capabilities with `base_value + (trait_multiplier * trait_value)` formula
- **ChallengeCategory, ChallengeTemplate** — atomic problems with severity, resolution type, and Properties M2M
- **ChallengeConsequence** — outcomes for success/failure/partial on a Challenge
- **ChallengeApproach** — links an Application to a Challenge with check type and optional effect property constraint
- **ApproachConsequence** — approach-specific consequence overrides
- **SituationTemplate** — composed groups of Challenges with narrative framing
- **SituationChallengeLink** — ordering and dependencies between Challenges in a Situation
- **SituationInstance, ChallengeInstance** — runtime instances tied to locations
- **CharacterChallengeRecord** — tracks character attempts and outcomes

### Data Models (magic app)
- **TechniqueCapabilityGrant** — links Techniques to Capabilities with `base_value + (intensity_multiplier * intensity)` formula, plus optional FK to PrerequisiteType

### Data Models (conditions app)
- **CapabilityType.prerequisite** — FK to PrerequisiteType, inherent prerequisites checked for ALL sources of a Capability
- **ConditionTemplate.properties M2M** — Properties temporarily granted while a condition is active

### Services (mechanics app)
- **`get_capability_sources_for_character(character)`** — collects per-source Capability values from Techniques, trait derivations, and conditions. Returns separate entries per source (no aggregation)
- **`get_available_actions(character, location)`** — matches Capability sources against active Challenges via Applications, returns AvailableAction list with difficulty indicators

### Types (mechanics app)
- **CapabilitySource** — tracks source type/name/id, value, effect properties, prerequisite key
- **AvailableAction** — full action description with application, approach, difficulty indicator
- **CooperativeAction** — placeholder for multi-character actions on the same Challenge

### Supporting Infrastructure
- Factories for all new models (mechanics and magic)
- Admin registrations with inlines for nested models
- 138 tests across mechanics (127), magic (7), and conditions (4)

## What's Needed for MVP

### Phase 1: Challenge Resolution (highest priority)
The models and action generation exist, but nothing actually resolves a Challenge yet.

- **`resolve_challenge()` service** — perform the check (via checks app), select consequences based on outcome, apply resolution. This is the core gameplay loop: character picks an action, system resolves it
- **Consequence application** — applying ChallengeConsequence outcomes: conditions granted/removed, damage dealt, Challenge state changes (destroyed, temporarily bypassed)
- **CharacterChallengeRecord creation** — recording what happened for history and preventing re-attempts where appropriate
- **Check integration** — connecting ChallengeApproach.check_type to the existing check resolution pipeline (traits app has CheckRank, ResultChart)

### Phase 2: Prerequisite System
PrerequisiteType exists as a SharedMemoryModel registry, with FKs from both CapabilityType and TechniqueCapabilityGrant, but nothing evaluates them yet.

- **Prerequisite registry** — a mapping from PrerequisiteType PK to callable checks that evaluate against the current Situation
- **Prerequisite evaluation in action generation** — filter out actions whose prerequisites aren't met before showing them to the player
- **Environmental prerequisites** — some prerequisites check room state (darkness, water present), others check character state (has line of sight, is standing)

### Phase 3: Cooperative Actions
The CooperativeAction dataclass exists but has no resolution logic.

- **Cooperative detection** — when multiple characters in the same location can address the same Challenge, surface cooperative options
- **Combined resolution** — how multiple characters' capability values combine for a cooperative attempt (additive? best-of? leader + support?)
- **Relationship bonuses** — relationship strength between cooperating characters should modify the combined result (ties into relationships app)

### Phase 4: Obstacle Migration
The obstacles app (`world/obstacles`) has a parallel system that predates Challenges. Both currently coexist.

- **Data migration** — convert ObstacleTemplate → ChallengeTemplate, ObstacleProperty → Property, BypassOption → ChallengeApproach, BypassCapabilityRequirement/BypassCheckRequirement → Application + approach constraints
- **CharacterBypassDiscovery/CharacterBypassRecord** → CharacterChallengeRecord
- **ObstacleInstance** → ChallengeInstance
- **Remove obstacles app** after migration is verified
- **Note:** No production data exists, so this is a code migration, not a data migration

### Phase 5: Attempts App Absorption
The attempts app (`world/attempts`) handles narrative consequence display. Its concepts map to ChallengeConsequence.

- **AttemptCategory** → ChallengeCategory (already exists)
- **AttemptTemplate** → ChallengeTemplate consequences
- **AttemptConsequence** → ChallengeConsequence (success/failure/partial outcomes already modeled)
- **Remove attempts app** after Challenge consequences prove themselves in gameplay
- **Roulette display** — the attempts app had a weighted narrative consequence display ("roulette"). Decide whether ChallengeConsequence needs similar weighted randomization or if deterministic outcomes are sufficient

### Phase 6: REST API & Frontend

- **API endpoints** — action generation endpoint (given character + location, return available actions), challenge resolution endpoint, situation browsing for GMs
- **Serializers** — for AvailableAction, ChallengeInstance, SituationInstance
- **Frontend: Action panel** — when a character is in a room with active Challenges, show available actions as interactive UI elements (context menu, action bar, or similar)
- **Frontend: Challenge resolution** — visual feedback for check results, consequence display, Challenge state changes
- **Frontend: GM Situation builder** — compose Challenges into Situations, assign Properties, set severity and consequences. This is the primary content creation tool for GMs

### Phase 7: Seed Data & Content Authoring
The system needs actual game content to be playable.

- **Core Properties** — elemental (flammable, frozen, electrified), physical (locked, breakable, heavy, armored), environmental (dark, underwater, elevated), creature (abyssal, celestial, undead)
- **Core CapabilityTypes** — ~20-30 capabilities covering the main action space (fire_generation, lockpicking, force, flight, healing, stealth, etc.)
- **Core Applications** — the eligibility matrix connecting capabilities to properties
- **Starter Challenges** — templates for common obstacles: locked doors, hostile creatures, environmental hazards, social barriers
- **TraitCapabilityDerivations** — which stats feed which capabilities (Strength → force, Dexterity → lockpicking, etc.)
- **Technique assignments** — TechniqueCapabilityGrants for existing Technique/Cantrip data

## Cross-System Integration

### Magic (world/magic)
- **TechniqueCapabilityGrant** already connects Techniques to Capabilities. When a character learns a new Technique, they automatically gain new action options
- **Effect properties** currently derived from Gift resonance names. May need direct effect property declarations on Techniques as the system matures
- **Intensity scaling** — higher-intensity Techniques produce higher capability values, making harder Challenges accessible
- **Cantrips** — CG cantrips create real Techniques, which means TechniqueCapabilityGrants on cantrip-generated Techniques give starting characters capabilities from day one
- **Post-CG technique builder** — new Techniques created post-CG need TechniqueCapabilityGrant assignment (manual via admin, or derived from effect type)

### Combat (world/combat — not yet built)
- Challenges model combat encounters: enemies are ChallengeTemplates with Properties (armored, flying, abyssal), attacks are ChallengeApproaches
- **Boss vulnerability windows** — a boss Challenge's available approaches change as the fight progresses (stage-based Properties that appear/disappear)
- **Combo attacks are separate** — structured attack combos are a dedicated combat mechanic, not derived from the Application pipeline. The Application system handles "what can you attempt", combos handle "how do sequential attacks chain"
- **Battle Scenes** — large-scale battles could model each round's decision as a Situation with Challenges representing strategic objectives

### Missions (world/missions — not yet built)
- **Mission stages map to SituationInstances** — each decision point in a branching mission is a Situation containing Challenges
- **SituationChallengeLink dependencies** model branching: completing one Challenge unlocks the next, with optional paths based on which approach was used
- **Mission generation** — randomly generated missions compose from ChallengeTemplate and SituationTemplate libraries
- **World consequences** — ChallengeConsequence outcomes feed into world state changes (territory shifts, alerts, reputation)

### Conditions (world/conditions)
- **ConditionTemplate.properties M2M** — active conditions grant Properties to characters (e.g., Werewolf Battleform grants "clawed", "bestial", "large"), expanding what Applications match
- **Condition-granted capabilities** — existing `get_all_capability_values()` feeds into `get_capability_sources_for_character()`
- **Conditions as consequences** — ChallengeConsequences can grant or remove conditions

### Character Progression (world/progression)
- **TraitCapabilityDerivation** means leveling up stats directly expands what actions are available
- **Path steps** — higher path levels could unlock new CapabilityTypes or increase derivation multipliers
- **Skill checks** — ChallengeApproach.check_type connects to the check pipeline where skill values matter

### Items & Equipment (not yet built)
- **Equipment as capability source** — items will be a fourth source type alongside techniques, traits, and conditions. A lockpick grants lockpicking capability; a fire sword grants fire_generation
- **Item Properties** — items themselves can have Properties (metallic, magical, fragile) making them targets for Challenges (e.g., a rust spell targets metallic items)

### Crafting (not yet built)
- **Crafting as Challenges** — crafting recipes could be modeled as Challenges where the crafter's capabilities determine quality outcomes
- **Material Properties** — crafting materials have Properties that determine what can be made from them

### Stories & GM Tables
- **GM content creation** — GMs author SituationTemplates and ChallengeTemplates to build adventure content
- **Story steps** — story beats reference Situations as mechanical tasks characters must complete
- **Trust-gated content** — higher-trust GMs can create Challenges with more severe consequences and broader world impact

### Societies & Organizations
- **Organization Properties** — an organization's territory or holdings could have Properties (fortified, sacred, corrupted) that affect what Challenges appear there
- **Reputation-gated approaches** — some ChallengeApproaches might require society reputation as a prerequisite

## Open Design Questions

These need resolution before or during implementation of later phases:

1. **Situation vs. existing obstacles relationship** — the obstacles app was built first and works. Migration path is clear but timing depends on when Challenges prove themselves in gameplay
2. **Attempt roulette** — should ChallengeConsequence support weighted randomization (like the attempts app's roulette display), or are deterministic consequences sufficient?
3. **Equipment capability source** — exact model for how items grant Capabilities (dedicated model like TechniqueCapabilityGrant, or Properties on items matched via Applications?)
4. **Difficulty tuning** — the current difficulty indicator is a simple ratio (capability_value / severity). Real gameplay may need more nuanced calculation incorporating skill levels, modifiers, and party composition
5. **Discovery mechanics** — how do characters discover hidden Challenges? Current ChallengeInstance.is_revealed flag exists but no discovery service
6. **Situation lifecycle** — when and how SituationInstances are created, activated, and cleaned up. Cron-based? Event-driven? GM-triggered?
7. **Cross-situation dependencies** — can Challenges in one Situation depend on outcomes in another? (e.g., mission stage 1 outcome affects stage 2 available approaches)

## Notes

### Architecture Reference
The full architecture doc at `docs/architecture/property-capability-action.md` contains detailed examples, the two-check pattern (availability check then application attempt), and extensive discussion of edge cases. Read it before implementing new phases.

### Implementation History
Phase 1 implementation (data models + services) completed on branch `docs/capability-application-architecture`. See `docs/plans/2026-03-15-capability-application-implementation.md` for the original implementation plan.
