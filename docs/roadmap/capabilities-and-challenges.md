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
- **ConsequenceEffect** — structured effects on consequences (condition, property, damage, flow, codex)
- **ObjectProperty** — runtime property on any game object with graduated value
- **ChallengeTemplateProperty** — through model adding value to challenge template properties

### Data Models (magic app)
- **TechniqueCapabilityGrant** — links Techniques to Capabilities with `base_value + (intensity_multiplier * intensity)` formula, plus optional FK to PrerequisiteType

### Data Models (conditions app)
- **CapabilityType.prerequisite** — FK to PrerequisiteType, inherent prerequisites checked for ALL sources of a Capability
- **ConditionTemplate.properties M2M** — Properties temporarily granted while a condition is active

### Services (mechanics app)
- **`get_capability_sources_for_character(character)`** — collects per-source Capability values from Techniques, trait derivations, and conditions. Returns separate entries per source (no aggregation)
- **`get_available_actions(character, location)`** — matches Capability sources against active Challenges via Applications, returns AvailableAction list with difficulty indicators
- **`resolve_challenge(character, challenge_instance, approach, capability_source)`** — thin wrapper: validates challenge state, delegates to generic pipeline for effect dispatch, handles challenge-specific bookkeeping (resolution_type, source_challenge provenance, records)
- **Effect handlers** for: APPLY_CONDITION, REMOVE_CONDITION, ADD_PROPERTY, REMOVE_PROPERTY, LAUNCH_FLOW, GRANT_CODEX (DEAL_DAMAGE and LAUNCH_ATTACK stubbed)

### Generic Consequence Pipeline (checks app)
- **`select_consequence(character, check_type, difficulty, consequences)`** — perform check, select weighted consequence from any pool, apply character loss filtering. Returns `PendingResolution` (not yet applied). Context-independent — usable by challenges, scenes, reactive checks, etc.
- **`apply_resolution(pending, context)`** — dispatch ConsequenceEffects via handlers using `ResolutionContext`. Returns list of `AppliedEffect` with optional `created_instance` for caller bookkeeping.
- **`ResolutionContext`** — carries typed optional refs (challenge_instance, action_context, future fields). Replaces direct ChallengeInstance coupling in effect handlers.
- **Two-step design** — separation of selection from application supports future reroll/negation mechanics.
- See `docs/architecture/check-resolution-spectrum.md` for how this fits the broader check pipeline.

### Types (mechanics app)
- **CapabilitySource** — tracks source type/name/id, value, effect properties, prerequisite key
- **AvailableAction** — full action description with application, approach, difficulty indicator
- **CooperativeAction** — placeholder for multi-character actions on the same Challenge

### Supporting Infrastructure
- Factories for all new models (mechanics and magic)
- Admin registrations with inlines for nested models
- 138 tests across mechanics (127), magic (7), and conditions (4)

## What's Needed for MVP

### Phase 1: Challenge Resolution (highest priority) — DONE
The core resolution loop is implemented end-to-end.

- **`resolve_challenge()` service** — DONE. Validates challenge state, delegates to generic consequence pipeline for effect dispatch, handles challenge-specific bookkeeping (resolution_type, source_challenge provenance, CharacterChallengeRecord)
- **Generic consequence pipeline** — DONE. `select_consequence()` + `apply_resolution()` in checks app. Decoupled from challenges — any system can map check results to weighted consequences. Two-step design supports future reroll/negation.
- **Consequence application** — DONE. ConsequenceEffect model with effect handlers for APPLY_CONDITION, REMOVE_CONDITION, ADD_PROPERTY, REMOVE_PROPERTY, LAUNCH_FLOW, GRANT_CODEX (DEAL_DAMAGE and LAUNCH_ATTACK stubbed pending combat system)
- **Character loss filtering** — DONE. Always applied regardless of consequence source (approach-level or template-level). Positive rollmod downgrades to worst non-loss alternative.
- **CharacterChallengeRecord creation** — DONE. Records approach used, check outcome, consequence selected, and whether resolution was successful
- **Check integration** — DONE. ChallengeApproach.check_type connects to `perform_check()` pipeline. Difficulty indicator uses rank-based calculation from the check system.

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

### Phase 4: Obstacle Migration — DONE
The obstacles app has been removed. `TraverseExitAction` now queries `ChallengeInstance` (INHIBITOR type) to block exits. No data migration was needed (no production data).

### Phase 5: Attempts App Absorption — DONE
Removed — challenge consequences now handle all narrative outcome selection.

### Phase 5.5: Consequence Pools for Non-Challenge Contexts
The generic consequence pipeline exists but consequence pools are currently only
authored via ChallengeTemplateConsequence and ApproachConsequence — attached to
challenge templates. For magic in social scenes, reactive checks (traps, poison),
and technique-inherent risks, GMs need consequence pools attached to other things.

**Key design decisions (from brainstorming):**
- Consequences from multiple independent sources (technique risk pool AND context
  pool) resolve independently — one `select_consequence()` call per pool
- Conflicts between pools handled at the effect level through idempotency (applying
  the same condition twice is a no-op, creating the same property twice is an upsert)
- No explicit exclusion tags or cross-pool conflict resolution for MVP
- Narrative contradictions are an authoring concern, not a system concern

**Needs design + implementation:**
- **Technique consequence pools** — a Technique (or TechniqueCapabilityGrant) can
  carry a mishap consequence pool. When the technique is used, the pool is resolved
  alongside whatever else is happening. E.g., a fire spell has a "wild magic" pool
  with consequences weighted by outcome tier.
- **Context consequence pools** — named, reusable consequence pools attached to
  Properties, rooms, or other environmental markers. "Using magic in a crowded
  tavern" triggers consequences from a pool attached to that context.
- **Model design** — could be a `ConsequencePool` container model (named collection
  of Consequences), or through-models on Technique/Property/etc. TBD — the container
  model is cleaner if pools are reused across multiple sources.
- **Admin UI** — GMs need to author these pools via Django admin with consequence
  weights, outcome tiers, and ConsequenceEffects.

**Open question:** Should consequence pools be freestanding named containers (a
`ConsequencePool` model that anything can FK to), or should each source type have
its own through-model (like ChallengeTemplateConsequence)? Freestanding is more
reusable but adds a layer of indirection. Through-models are explicit but proliferate.

### Phase 5.6: Scene Check Integration
The check system and consequence pipeline are ready, but there's no way for a
player to trigger a check within a scene context.

**What the architecture says** (check-resolution-spectrum.md):
- Social scene checks use `perform_check()` directly for narrative-only results
- Risky actions (magic, high-stakes social) use `select_consequence()` +
  `apply_resolution()` for structured consequences
- Scene system handles display, not the consequence pipeline

**Needs design + implementation:**
- **Action-attached poses** — player writes a pose and attaches a mechanical check.
  UI for selecting what kind of check to make (or the system infers from the action).
- **Scene consequence trigger** — when a player uses a technique or risky action in
  a scene, the system resolves consequence pools from the technique and/or context.
  Builds a `ResolutionContext` with `action_context` populated.
- **Inline result display** — check results and consequences display inline in scene
  narrative. Players see what happened; GM consequences fire automatically.
- **No Situation required** — this works outside of Situations. A character casts a
  spell at a party and something goes wrong. No ChallengeInstance needed.

### Phase 5.7: Situation Runtime
The Situation and Challenge models exist but there is no runtime lifecycle.

**Needs design (open question #5):**
- When and how SituationInstances are created (GM trigger? event-driven? room entry?)
- How Challenges are revealed to players (all visible? progressive discovery?)
- How SituationChallengeLink dependencies work at runtime (completing one Challenge
  unlocks the next)
- Instance lifecycle and cleanup (when do they deactivate/disappear?)
- How scene FK works (Situation tied to active scene recording?)

### Phase 5.8: Reroll and Negation Mechanics
The two-step pipeline (`select_consequence` then `apply_resolution`) was designed
to support intervention between selection and application.

**Needs design:**
- How players spend resources to reroll (what resources? AP? special abilities?)
- How abilities negate specific consequence types (e.g., fire resistance negates
  burn consequences)
- UI for presenting the pending consequence and offering intervention options
- Whether rerolls use the same pool or a modified one
- Cost scaling (rerolling a critical failure costs more than rerolling a mild one?)

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

1. ~~**Consequence randomization**~~ — RESOLVED. Yes, weighted randomization. The generic consequence pipeline uses `select_weighted()` with per-consequence weights within each outcome tier. Character loss filtering provides safety. Roulette display data is built by callers via `build_outcome_display()`.
2. **Equipment capability source** — exact model for how items grant Capabilities (dedicated model like TechniqueCapabilityGrant, or Properties on items matched via Applications?)
3. ~~**Difficulty tuning**~~ — RESOLVED. Rank-based calculation via `preview_check_difficulty()`. Uses the same CheckRank pipeline as actual checks. IMPOSSIBLE filtering hides actions where the ResultChart has no success outcomes.
4. **Discovery mechanics** — how do characters discover hidden Challenges? Current ChallengeInstance.is_revealed flag exists but no discovery service
5. **Situation lifecycle** — when and how SituationInstances are created, activated, and cleaned up. Cron-based? Event-driven? GM-triggered? (See Phase 5.7)
6. **Cross-situation dependencies** — can Challenges in one Situation depend on outcomes in another? (e.g., mission stage 1 outcome affects stage 2 available approaches)
7. **Consequence pool model** — freestanding `ConsequencePool` container vs per-source through-models. Affects authoring UX and reusability. (See Phase 5.5)
8. **Cooperative resolution** — how do multiple independent rolls combine into a cooperative outcome? Count successes, average tiers, best/worst with support modifiers? (See Phase 3)
9. **Reroll/negation resources** — what do players spend to intervene between consequence selection and application? AP? Special abilities? Luck tokens? (See Phase 5.8)

## Notes

### Architecture Reference
The full architecture doc at `docs/architecture/property-capability-action.md` contains detailed examples, the two-check pattern (availability check then application attempt), and extensive discussion of edge cases. Read it before implementing new phases.

### Implementation History
Phase 1 implementation (data models + services) completed on branch `docs/capability-application-architecture`. See `docs/plans/2026-03-15-capability-application-implementation.md` for the original implementation plan.
