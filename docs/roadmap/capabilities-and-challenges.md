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

### Data Models (actions app)
- **ConsequencePool** — named, reusable consequence collections with optional single-depth parent inheritance
- **ConsequencePoolEntry** — links Consequence to Pool with optional weight override or exclusion flag for inheritance customization
- **ActionTemplate** — data-driven resolution specification: check type + consequence pool + pipeline pattern (SINGLE or GATED)
- **ActionTemplateGate** — optional prerequisite check steps gating an ActionTemplate's main resolution

### Data Models (mechanics app, continued)
- **ContextConsequencePool** — links a ConsequencePool to a Property for environmental consequences (rider mode for player actions, reactive mode for traps/hazards)
- **ChallengeApproach.action_template** — nullable FK to ActionTemplate. When set, `resolve_challenge()` delegates to the template's pipeline instead of inline resolution

### Data Models (magic app)
- **TechniqueCapabilityGrant** — links Techniques to Capabilities with `base_value + (intensity_multiplier * intensity)` formula, plus optional FK to PrerequisiteType
- **Technique.action_template** — nullable FK to ActionTemplate for using techniques outside challenge contexts (social scenes, freeform magic)

### Data Models (conditions app)
- **CapabilityType.prerequisite** — FK to PrerequisiteType, inherent prerequisites checked for ALL sources of a Capability
- **ConditionTemplate.properties M2M** — Properties temporarily granted while a condition is active

### Services (mechanics app)
- **`get_capability_sources_for_character(character)`** — collects per-source Capability values from Techniques, trait derivations, and conditions. Returns separate entries per source (no aggregation)
- **`get_available_actions(character, location)`** — matches Capability sources against active Challenges via Applications, returns AvailableAction list with difficulty indicators
- **`resolve_challenge(character, challenge_instance, approach, capability_source)`** — thin wrapper: validates challenge state, delegates to generic pipeline for effect dispatch, handles challenge-specific bookkeeping (resolution_type, source_challenge provenance, records)
- **Effect handlers** for: APPLY_CONDITION, REMOVE_CONDITION, ADD_PROPERTY, REMOVE_PROPERTY, LAUNCH_FLOW, GRANT_CODEX, MAGICAL_SCARS (DEAL_DAMAGE and LAUNCH_ATTACK stubbed)

### Generic Consequence Pipeline (checks app)
- **`select_consequence(character, check_type, difficulty, consequences)`** — perform check, select weighted consequence from any pool, apply character loss filtering. Returns `PendingResolution` (not yet applied). Context-independent — usable by challenges, scenes, reactive checks, etc.
- **`select_consequence_from_result(character, check_result, consequences)`** — same as above but reuses an existing CheckResult instead of rolling. Used for context pools sharing the main action's roll.
- **`apply_resolution(pending, context)`** — dispatch ConsequenceEffects via handlers using `ResolutionContext`. Returns list of `AppliedEffect` with optional `created_instance` for caller bookkeeping.
- **`ResolutionContext`** — carries typed optional refs (challenge_instance, action_context, future fields). Replaces direct ChallengeInstance coupling in effect handlers.
- **Two-step design** — separation of selection from application supports future reroll/negation mechanics.
- See `docs/architecture/check-resolution-spectrum.md` for how this fits the broader check pipeline.

### Resolution Pipeline (actions app)
- **`get_effective_consequences(pool)`** — resolves pool inheritance into a flat list of `WeightedConsequence` objects. Handles parent entries, child exclusions, weight overrides.
- **`start_action_resolution(character, template, difficulty, context)`** — starts the state machine pipeline. Runs gates (for GATED templates), main step, and context pools. Returns `PendingActionResolution` which may be paused (awaiting_confirmation) or complete.
- **`advance_resolution(pending, context, player_decision)`** — resumes a paused pipeline. Supports confirm, abort, and reroll decisions.
- **`PendingActionResolution`** — serializable state of an in-progress resolution with gate results, main result, context results, and pause flags.
- **App responsibility split:** Actions owns "what happens" (resolution specs, pools); Mechanics owns "when it's available" (eligibility, context); Checks owns "how rolls work" (check resolution, consequences).

### Types (mechanics app)
- **CapabilitySource** — tracks source type/name/id, value, effect properties, prerequisite key
- **AvailableAction** — full action description with application, approach, difficulty indicator
- **CooperativeAction** — placeholder for multi-character actions on the same Challenge

### CharacterEngagement (mechanics app)
- **CharacterEngagement** — OneToOne to ObjectDB tracking what a character is actively
  doing that has stakes (CHALLENGE, COMBAT, MISSION). Observable by other characters.
- Process modifier fields: `intensity_modifier`, `control_modifier` for transient
  bonuses from escalation, Audere, combat events. Separate from identity-derived
  CharacterModifier records.
- `escalation_level` — incremented by the engaging system, translates to intensity bonus
- Generic FK source (ContentType + source_id) for flexible engagement sources

### Supporting Infrastructure
- Factories for all new models (actions, mechanics, magic), including `ChallengeInstanceFactory` and `SituationInstanceFactory`
- Admin registrations with inlines for nested models (actions, mechanics)
- **Pipeline integration tests** (`world/mechanics/tests/test_pipeline_integration.py`) — end-to-end tests across 5 classes (ChallengePathTests, SceneActionPathTests, GatedPipelineTests, TechniqueUseFlowTests, RuntimeModifierTests) validating the full technique → capability → application → resolution pipeline, including runtime modifier streams and Audere lifecycle. These are designed to grow as new systems come online. Spec: `docs/architecture/integration-test-patterns.md`
- **API endpoint tests** (`world/mechanics/tests/test_api.py`) — 20 tests covering all Phase 6a endpoints, filters, and permission enforcement
- **Permission tests** (`web/api/tests/test_permissions.py`) — 6 tests for `IsCharacterOwner` permission class

## What's Needed for MVP

### Phase 1: Challenge Resolution (highest priority) — DONE
The core resolution loop is implemented end-to-end.

- **`resolve_challenge()` service** — DONE. Validates challenge state, delegates to generic consequence pipeline for effect dispatch, handles challenge-specific bookkeeping (resolution_type, source_challenge provenance, CharacterChallengeRecord)
- **Generic consequence pipeline** — DONE. `select_consequence()` + `apply_resolution()` in checks app. Decoupled from challenges — any system can map check results to weighted consequences. Two-step design supports future reroll/negation.
- **Consequence application** — DONE. ConsequenceEffect model with effect handlers for
  APPLY_CONDITION, REMOVE_CONDITION, ADD_PROPERTY, REMOVE_PROPERTY, LAUNCH_FLOW,
  GRANT_CODEX (DEAL_DAMAGE and LAUNCH_ATTACK stubbed pending combat system).
  Dynamic-reshaping effect types added in #1018 (see "Positioning reshape effects" below).
- **Character loss filtering** — DONE. Always applied regardless of consequence source (approach-level or template-level). Positive rollmod downgrades to worst non-loss alternative.
- **CharacterChallengeRecord creation** — DONE. Records approach used, check outcome, consequence selected, and whether resolution was successful
- **Check integration** — DONE. ChallengeApproach.check_type connects to `perform_check()` pipeline. Difficulty indicator uses rank-based calculation from the check system.
- **Capability modifiers folded into checks** (#2505) — DONE. `CheckTypeCapabilityModifier`
  (curated, authored `(check_type, capability)` pairs, `world/checks/models.py`) lets a
  CheckType read the agency oracle (`get_effective_capability_value`) directly — an authored
  row contributes `weight x effective_capability_value` (summed, truncated toward zero) into
  `perform_check`'s `total_points`, alongside a `CAPABILITY`-kind `ModifierContribution` in
  `collect_check_modifiers`'s provenance. `resolve_challenge()` also folds its
  `capability_source.value` (the technique/trait/condition/item capability that chose the
  approach) directly into `extra_modifiers` before calling `perform_check` — the two
  capability oracles (availability's technique-grant read vs. this agency-value read) now both
  reach the roll.

### Phase 2: Prerequisite System — DONE
Prerequisites are now data-driven property checks, not code-dispatched callables.

**What was built:**
- **Renamed PrerequisiteType → Prerequisite** with new fields: `property` (FK to Property),
  `property_holder` (SELF/TARGET/LOCATION), `minimum_value` (threshold for graduated checks).
  The `evaluate()` method queries ObjectProperty on the resolved entity.
- **ChallengeInstance.target_object** — non-nullable FK to ObjectDB. Every challenge is embodied
  by a world object (boulder, door, ward, etc.), enabling TARGET prerequisite checks.
- **Two-level evaluation in get_available_actions()** — capability-level prerequisites (cached
  per capability_id) and source-level prerequisites (per TechniqueCapabilityGrant). Failed
  prerequisites still return AvailableActions with `prerequisite_met=False` and reasons for
  frontend display as disabled actions.
- **CapabilitySource carries Prerequisite instance** directly (not bare PK).
- **Integration tests** — 3 new tests covering met/not-met/no-prerequisite cases.

**Key design decisions:**
- Data-driven over code-driven — most prerequisites are "does [entity] have [property] at
  [value]?" No callable registry, no import paths, no Python functions for the common case.
- Failed-prerequisite actions are returned (not filtered) so the frontend can show them grayed
  out with reasons ("Requires primal_attuned on Character").
- Challenge objects enable TARGET prerequisites and open future typeclass design for obstacle
  types with class-level properties.

**Still needed (future work):**
- `service_function_path` escape hatch for truly bespoke prerequisites (Thread-based checks,
  resource checks) — add when the first case arises
- Challenge object typeclasses (obstacles, hazards, wards) with class-level properties
- Frontend display of disabled actions with prerequisite reasons
- Prerequisite evaluation in scene action path (currently challenge path only)

**Design spec:** `docs/architecture/prerequisite-evaluation.md`

### Phase 3: Cooperative Actions
The CooperativeAction dataclass exists but has no resolution logic.

- **Cooperative detection** — when multiple characters in the same location can address the same Challenge, surface cooperative options
- **Combined resolution** — how multiple characters' capability values combine for a cooperative attempt (additive? best-of? leader + support?)
- **Relationship bonuses** — relationship strength between cooperating characters should modify the combined result (ties into relationships app)

### Phase 4: Obstacle Migration — DONE
The obstacles app has been removed. `TraverseExitAction` now queries `ChallengeInstance` (INHIBITOR type) to block exits. No data migration was needed.

### Phase 5: Attempts App Absorption — DONE
Removed — challenge consequences now handle all narrative outcome selection.

### Phase 5.5: Consequence Pools & Action Templates — DONE
Consequence pools are now authorable independent of challenges. ActionTemplate
provides a unified resolution specification for any data-driven action.

**What was built:**
- **ConsequencePool** — freestanding named container with single-depth inheritance.
  Child pools add, exclude, or override weights from a parent pool. Resolved via
  `get_effective_consequences()` into flat `WeightedConsequence` lists.
- **ActionTemplate** — data-driven resolution spec carrying check_type, consequence
  pool, and pipeline pattern (SINGLE or GATED). The counterpart to code-defined
  Actions for authored content (techniques, combat abilities, rituals).
- **ActionTemplateGate** — optional prerequisite checks (activation, etc.) that gate
  an ActionTemplate's main resolution. Failure can abort the pipeline.
- **ContextConsequencePool** — links pools to Properties for environmental effects.
  Rider mode (fires alongside player actions, shares check result) and reactive
  mode (fires independently with own check type, e.g., traps).
- **Resolution pipeline** — state machine (`start_action_resolution` / `advance_resolution`)
  with pause points for pre-check confirmation (character loss risk) and post-selection
  intervention (future reroll). Context pools resolve using the main step's check result.
- **resolve_challenge() delegation** — when a ChallengeApproach has an ActionTemplate,
  resolution delegates to the template pipeline. Existing approaches without templates
  continue working unchanged.
- **Admin UI** — Django admin for ConsequencePool (with inline entries) and ActionTemplate
  (with inline gates).

**Key design decisions:**
- Freestanding ConsequencePool container model — pools reused across sources
- Single-depth inheritance — child pools patch parent, no grandparent chains
- Action pool and context pool resolve independently using same check result
- Reactive processing (defense, counterattack) is receiver-side — separate concern
- Pipeline patterns are code-defined (SINGLE, GATED); data fills them via templates
- Event emission at pipeline pause points deferred — architecture accommodates it

**Still needed (future phases):**
- **Event/trigger integration** — intent events before resolution, result events after.
  Enables wards, protective effects, environmental reactions. Pause point architecture
  supports this. See design spec for event integration section.
- **Reroll mechanics** — pipeline supports reroll as a decision; resource costs and
  availability from Kudos/PlayerTrust system.
- **SyntheticAction** — wrapping ActionTemplate into a full Action with `run()` lifecycle,
  prerequisites, and enhancements. Bridges code-defined and data-driven action systems.
- **ChallengeApproach migration** — gradually make all approaches use ActionTemplate,
  eventually making the FK non-nullable.
- **Context pool wiring** — `_run_context_pools()` is implemented but not yet called
  in the pipeline. Needs ObjectProperty query integration.

**Design spec:** `docs/architecture/action-template-pipeline.md`

### Phase 5.6: Scene Check Integration — DONE
Players can use techniques and social actions within scenes, with consent-based
targeting and mechanical consequences.

**What was built:**
- **InteractionAudience refactor** — replaced per-viewer audience rows with
  InteractionReceiver (only for private interactions). Added Place model for
  sub-location scoping within rooms. Dramatically reduces storage for the
  highest-volume table.
- **Scene action system** — action-first flow where players select an action,
  the check resolves, then they write narrative. Self-targeted actions resolve
  immediately; targeted actions go through an OOC consent flow.
- **Consent mechanism** — SceneActionRequest tracks the lifecycle. Target player
  sets difficulty via their consent level (deny/easy/standard/hard). Higher
  cooperation earns more Kudos (future integration).
- **Social action stubs** — 6 code-defined social actions (intimidate, persuade,
  deceive, flirt, perform, entrance) with technique enhancement slots.
- **resolve_scene_action()** — glue between scenes and the action/check pipeline.
  Creates ACTION-mode Interactions with check results.
- **Micro-scene auto-creation** — ensure_scene_for_location creates placeholder
  scenes for spontaneous interactions.
- **REST API** — available-actions, action-requests (create/list/respond), places
  (list/join/leave) endpoints.
- **Frontend** — ActionPanel (floating action button), PersonaContextMenu
  (right-click targeting), ConsentPrompt (OOC consent banner), ActionResult
  (ACTION interaction display), PlaceBar (sub-location navigation).

**Key design decisions:**
- Action-first flow (resolve check, then narrate) — natural for RP
- Consent is OOC (system prompt, not IC interaction)
- Difficulty from consent (target player controls difficulty)
- Places are persistent room features, not scene-scoped
- Scenes as universal containers (micro-scene auto-creation)
- Social actions as categories with technique enhancement slots

**Still needed (future phases):**
- **Action permission presets** — players pre-set consent rules per action category
- **Kudos integration** — reward system for consenting to targeted actions
- **Entrance pose voting** — facet feedback on entrance poses
- **Social properties on characters** — full Application matching for social actions
- **Social CheckTypes** — need seed data so social action checks produce results

### Phase 5.6b: Technique-Enhanced Social Actions — DONE
Social actions now integrate the full technique use pipeline, allowing players
to enhance mundane social actions with magical techniques.

**What was built:**
- **Full consequence pipeline** — All 6 social actions (intimidate, persuade,
  deceive, flirt, perform, entrance) use `start_action_resolution()` with
  consequence pools instead of bare pass/fail. Mundane actions apply any
  consequence effect type: conditions, properties, codex grants, flows.
- **ActionEnhancement model** — links a social action to a Technique. When
  selected, wraps the action in `use_technique()`, deducting anima, evaluating
  Soulfray severity, and checking for control mishaps before resolution.
- **Technique effects as distinct results** — ActionResult renders both the
  social outcome (persuade result, condition applied) and technique effects
  (anima cost, Soulfray stage change, control mishap conditions) as separate
  result blocks.
- **Available-actions enhancement data** — `available_actions` endpoint includes
  `action_enhancements` per social action with pre-calculated anima costs and
  current Soulfray stage warning. Players see all techniques available for each
  action at a glance.
- **Frontend enhancement selection** — ActionPanel shows technique enhancements
  with anima cost display and Soulfray warning confirmation dialog before
  technique use. Results display is layered per effect type.
- **Integration tests** — Comprehensive coverage of mundane path, enhancement path,
  validation errors, and available-actions filtering.

**Design spec:** `docs/superpowers/specs/2026-03-22-scene-checks-and-interaction-refactor-design.md`

### Phase 5.7: Situation Runtime
The Situation and Challenge models exist but there is no runtime lifecycle.

**Traps and Challenges: solved (#1625, #1895).** `SituationTrapLink` +
`SituationChallengeLink.target_object_name` + `instantiate_situation()`
(`world/mechanics/situation_services.py`) mint both into real `Trap` and
`ChallengeInstance` rows. The GM trigger mechanism is also solved (#1895):
`SetSituationAction` + `CmdSetSituation`, mirroring `SetTheStageAction`.

**Still needs design:**
- How SituationChallengeLink dependencies work at runtime (completing one
  Challenge unlocks the next)
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

### Phase 6: REST API & Frontend — PARTIALLY DONE

#### Phase 6a: Read-Only API — DONE

**What was built:**
- **`AvailableActionsView`** *(superseded — see note below)* — `ListAPIView` at
  `GET /api/mechanics/characters/{character_id}/available-actions/` with optional
  `?location_id=` override. Calls `get_available_actions()`, groups results by
  challenge into `ChallengeGroup` dataclasses, returns paginated list.
  **Superseded by the unified `GET /api/actions/characters/<id>/available/` endpoint**
  (branch `unified-action-interface`, combat.md Phase 7). The mechanics endpoint is
  deleted; `get_available_actions()` is still called internally by `get_player_actions()`.
- **`IsCharacterOwner`** — reusable permission class in `web/api/permissions.py`.
  Checks `RosterTenure` for active tenure via character ID in URL kwargs. Staff
  bypass. Usable by any endpoint that takes a character ID.
- **Read-only model ViewSets** — `ChallengeTemplateViewSet`,
  `ChallengeInstanceViewSet`, `SituationTemplateViewSet`,
  `SituationInstanceViewSet`. All `ReadOnlyModelViewSet` with FilterSets,
  `MechanicsPagination` (20/page), list/detail serializer splits, and proper
  `Prefetch` with `to_attr` + `cached_property` for detail views.
- **`djangorestframework-dataclasses`** — adopted for DRY dataclass serialization.
  `DataclassSerializer` for `CapabilitySource`, `AvailableAction`,
  `ChallengeGroup`. Also converted `DispatcherDescriptorSerializer` and
  `CommandDescriptorSerializer` in the flows app.
- **FilterSet extraction** — all mechanics FilterSets moved to `filters.py`.
  Existing `CharacterModifierViewSet` migrated from bare `filterset_fields` to
  proper `FilterSet` class.
- **20 API tests + 6 permission tests** covering all endpoints, permissions,
  filters, and edge cases.

**Design spec:** `docs/architecture/mechanics-api.md`

#### Phase 6b: Still needed

- **Challenge resolution endpoint** — POST endpoint for resolving a challenge approach (mutation, consent flow)
- **Frontend: Action panel** — when a character is in a room with active Challenges, show available actions as interactive UI elements (context menu, action bar, or similar)
- **Frontend: Challenge resolution** — visual feedback for check results, consequence display, Challenge state changes
- **Frontend: GM Situation builder** — compose Challenges into Situations, assign Properties, set severity and consequences. This is the primary content creation tool for GMs

### Phase 7: Seed Data & Content Authoring

**Pass 1 — Social Action Content: COMPLETE** (PR #???; branch `feature/phase7-social-integration-tests`)

Built a content authoring layer that makes all 6 social actions fully playable with real consequences:

- **`src/integration_tests/game_content/`** — centralized content builder package:
  - `checks.py` — `CheckContent`: thin wrapper around existing social check type / action template factories
  - `conditions.py` — `ConditionContent`: 6 named social conditions (Shaken, Charmed, Deceived, Smitten, Captivated, Enthralled)
  - `social.py` — `SocialContent.create_all()`: wires consequence pools to action templates; ConsequenceEffects apply conditions to `EffectTarget.TARGET` on success
  - `characters.py` — `CharacterContent.create_base_social_character()`: character with social traits + PRIMARY persona
- **`src/integration_tests/pipeline/test_social_pipeline.py`** — 10 end-to-end tests across 3 classes: availability, consent flow, consequence application
- **`EffectTarget.TARGET`** added to `world/checks/constants.py` + migration + `_resolve_target` dispatch + `ResolutionContext.target` field

**Pass 2 — Magic / Technique Content: COMPLETE**

Built technique-enhanced social actions with full anima deduction and condition consequences:

- **`src/integration_tests/game_content/magic.py`** — `MagicContent.create_all()`: 6 Techniques (intensity=2, control=2, anima_cost=12) + 6 `ActionEnhancement` records linking each technique to its social action; `grant_techniques_to_character()` creates `CharacterTechnique` records
- **`src/actions/factories.py`** — `ActionEnhancementFactory` added
- **`src/integration_tests/pipeline/test_social_magic_pipeline.py`** — 6 end-to-end tests across 2 classes:
  - `SocialMagicAvailabilityTests`: known techniques appear in `get_available_scene_actions`; correct technique linked per action; no-technique characters have no enhancements
  - `SocialMagicConsequenceTests`: enhanced intimidate applies Shaken to target (not initiator); anima deducted from initiator (effective_cost=2 after social_safety=10 bonus); `technique_result` present on result
- **Note on social safety bonus**: `_get_social_safety_bonus()` returns +10 control for unengaged characters; `anima_cost=12` was chosen so `effective_cost = max(12 - 10, 0) = 2` — predictable non-zero deduction for tests

**Pass 3 — Capability / Challenge Content: COMPLETE**

Built capability and challenge content layer exercising the full pipeline end-to-end:

- **`src/integration_tests/game_content/challenges.py`** — `ChallengeContent.create_all()`:
  19 CapabilityTypes (12 physical/magical + 5 social + 2 mental), 5 PropertyCategories
  with 27 Properties, 44 Applications (capability + property eligibility pairs),
  5 ChallengeCategories, 6 starter ChallengeTemplates with approaches and consequence
  pools, 5 non-social CheckTypes, 11 TraitCapabilityDerivations (placeholder values)
- **`src/integration_tests/game_content/magic.py`** — extended MagicContent with
  `create_elemental_techniques()` (4 techniques: Flame Lance, Shadow Step, Stone Ward,
  Gale Burst with TechniqueCapabilityGrants) and `wire_social_technique_capabilities()`
  (grants on all 6 social techniques)
- **`src/integration_tests/game_content/characters.py`** — added
  `create_base_challenge_character()` for physical/mental stat testing
- **`src/integration_tests/pipeline/test_challenge_pipeline.py`** — 14 end-to-end tests
  across 3 classes: ChallengeAvailabilityTests (trait-derived capability matching),
  TechniqueChallengePipelineTests (full technique → capability → application → approach),
  ChallengeResolutionTests (consequence application and record creation)
- **Key design decisions**: Capabilities are atomic single-verb primitives (no compound
  names like fire_generation). Social capabilities (5) are distinct from physical (12)
  and mental (2) — different end states justify separate primitives. Mental stats do NOT
  derive social capabilities (balance). TraitCapabilityDerivation values are placeholders.
- **Pipeline finding**: `get_available_actions` requires the Application's target_property
  to appear on the challenge's Properties. ChallengeApproaches whose Application references
  a property not on the challenge (e.g., Solve/analysis+mechanical on a door with locked/solid/breakable)
  are correctly filtered out. Approaches must be designed with property overlap in mind.

## Cross-System Integration

### Magic (world/magic)
- **TechniqueCapabilityGrant** already connects Techniques to Capabilities. When a character learns a new Technique, they automatically gain new action options
- **Effect properties** linked to Resonances via M2M (Resonance.properties, refactored from name-matching in PR #360). May need direct effect property declarations on Techniques as the system matures
- **Intensity scaling** — higher-intensity Techniques produce higher capability values, making harder Challenges accessible
- **CG catalog techniques** — CG links characters to authored catalog `Technique` rows (Path × Gift starter pool, #2426), which means TechniqueCapabilityGrants on those catalog Techniques give starting characters capabilities from day one
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

### Positioning Reshape Effects — DONE (#1018)

Six new `EffectType` values handle dynamic battlefield changes as structured consequence
effects dispatched by `apply_resolution` / `world/mechanics/effect_handlers.py`.  They
resolve entirely within the actor's current room at apply time; no FK to a per-room runtime
`Position` is stored on the `ConsequenceEffect` row.

**New EffectType values** (`world/checks/constants.py`):

| EffectType | Handler | What it does |
|------------|---------|--------------|
| `CREATE_POSITION` | `_create_position` | Create a new `Position` (kind defaults to FEATURE); optionally connect it to the actor's current position (`position_connect_from_actor`) and move a target into it (`position_place_occupant`); emits `FELL` if the new position is a CHASM **and** `position_place_occupant=True` (an occupant is placed into it) |
| `MOVE_TO_POSITION` | `_move_to_position` | Force-move the resolved target to the destination position; destination is resolved via `PositionDestination` (see below); emits `FELL` if destination is a CHASM |
| `SEVER_EDGE` | `_sever_edge` | Disconnect the edge between two named positions in the room; skips gracefully if either endpoint or the edge is absent |
| `CONNECT_EDGE` | `_connect_edge` | Connect two named positions (idempotent — no-op when an edge already exists) |
| `GRANT_FLIGHT` | `_grant_flight` | Call `enter_aerial(target)` — materializes the aerial layer and moves the target to the AERIAL twin above their current position |
| `REMOVE_FLIGHT` | `_remove_flight` | Call `leave_aerial(target)` — returns the target to their anchor ground position and clears the `"aerial"` property |

**`PositionDestination`** (`world/checks/constants.py`) — governs how `MOVE_TO_POSITION`
resolves its target position:

| Value | Meaning |
|-------|---------|
| `ACTOR_POSITION` | The actor's current position at apply time |
| `GATING_FAR_SIDE` | The far-side endpoint of the gating edge whose `gating_challenge` matches `context.challenge_instance` — used for gated-crossing consequences |
| `NAMED` | A position looked up by `effect.position_name` in the actor's room |

**`ConsequenceEffect` positioning columns** (all in `world/checks/models.py`):

| Field | Relevant for |
|-------|-------------|
| `position_name` | `CREATE_POSITION` (the new node's name); `SEVER_EDGE` / `CONNECT_EDGE` (first endpoint); `MOVE_TO_POSITION` + NAMED destination |
| `position_name_b` | `SEVER_EDGE` / `CONNECT_EDGE` second endpoint |
| `position_kind` | `CREATE_POSITION` — `PositionKind` for the new node (default: FEATURE) |
| `position_description` | `CREATE_POSITION` — description text for the new node |
| `position_destination` | `MOVE_TO_POSITION` — `PositionDestination` value |
| `position_connect_from_actor` | `CREATE_POSITION` — when True, connect the new node to the actor's current position (default True) |
| `position_place_occupant` | `CREATE_POSITION` — when True, force-move the resolved target into the new node |

**`FELL` event seam:** `maybe_emit_fall(objectdb, position)` is called by `_create_position`
and `_move_to_position` whenever the resulting position is a `CHASM`.  It emits
`EventName.FELL` (`FallEvent(faller, position)`) via the reactive layer.  The reactive
consumer is **built (#1228)**: `begin_plummet` ensures an AFK-safe STRICT danger round (#1466)
+ applies `Plummeting` + binds the catch challenge; `advance_plummet` descends/impacts per round; and
`dispatch_catch` → `resolve_catch` lets a capability-gated bystander catch the faller (clean
catch ends the plummet with no impact and places the faller safely). See
`docs/systems/areas.md` for the full pipeline.

## Open Design Questions

These need resolution before or during implementation of later phases:

1. ~~**Consequence randomization**~~ — RESOLVED. Yes, weighted randomization. The generic consequence pipeline uses `select_weighted()` with per-consequence weights within each outcome tier; outcome-display data is built by callers via `build_outcome_display()` from the full resolved pool.
2. **Equipment capability source** — exact model for how items grant Capabilities (dedicated model like TechniqueCapabilityGrant, or Properties on items matched via Applications?)
3. ~~**Difficulty tuning**~~ — RESOLVED. Rank-based calculation via `preview_check_difficulty()`. Uses the same CheckRank pipeline as actual checks. IMPOSSIBLE filtering hides actions where the ResultChart has no success outcomes.
4. **Discovery mechanics** — how do characters discover hidden Challenges? Current ChallengeInstance.is_revealed flag exists but no discovery service
5. **Situation lifecycle** — creation is resolved (GM-triggered via `SetSituationAction`/`CmdSetSituation`, #1895); activation/cleanup (when do instances deactivate or disappear?) is still open. (See Phase 5.7)
6. **Cross-situation dependencies** — can Challenges in one Situation depend on outcomes in another? (e.g., mission stage 1 outcome affects stage 2 available approaches)
7. ~~**Consequence pool model**~~ — RESOLVED. Freestanding `ConsequencePool` container with single-depth inheritance. Pools are reused across techniques, challenges, and environmental contexts. ActionTemplate carries the pool FK; ContextConsequencePool links pools to Properties.
8. **Cooperative resolution** — how do multiple independent rolls combine into a cooperative outcome? Count successes, average tiers, best/worst with support modifiers? (See Phase 3)
9. **Reroll/negation resources** — what do players spend to intervene between consequence selection and application? AP? Special abilities? Luck tokens? (See Phase 5.8)

## Notes

### Architecture Reference
The full architecture doc at `docs/architecture/property-capability-action.md` contains detailed examples, the two-check pattern (availability check then application attempt), and extensive discussion of edge cases. Read it before implementing new phases.

### Implementation History
Phase 1 implementation (data models + services) completed on branch `docs/capability-application-architecture`. See `docs/plans/2026-03-15-capability-application-implementation.md` for the original implementation plan.

Phase 5.5 implementation (consequence pools + action templates) completed on branch `feature/consequence-pools-action-templates`. Design spec at `docs/architecture/action-template-pipeline.md`.
