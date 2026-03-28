# Pipeline Integration Test Design

## Purpose

Validate the full technique-to-resolution pipeline end-to-end across both resolution paths:
1. **Challenge path**: Technique → CapabilityGrant → Application → Challenge → resolve_challenge()
2. **Scene action path**: Technique → ActionTemplate → SceneActionRequest → resolve_scene_action()

These paths share check infrastructure but diverge in how they enter resolution:
- Challenge path uses `get_available_actions()` for discovery and `resolve_challenge()` for
  resolution, with consequence selection from ChallengeTemplateConsequence/ApproachConsequence.
- Scene action path uses `respond_to_action_request()` → `resolve_scene_action()`, which
  calls `perform_check()` directly against the ActionTemplate's check_type. Currently this
  path does NOT use consequence pools or `start_action_resolution()` — it returns a simple
  SceneActionResult with pass/fail. The gated pipeline (`start_action_resolution`) is a
  separate entry point used by `_resolve_via_template` in challenge resolution.

This divergence is itself a finding worth documenting: scene actions are simpler than
challenge resolution today. As the system matures, scene actions may gain consequence
pools and gated pipelines, but the test should reflect what actually exists.

These integration tests represent the boundaries of what the system can do today. They should
grow as new systems are added — they are the living proof that the pipeline connects.

### Design Principles

- **Realistic complexity**: Multiple capability grants, prerequisites, effect property filtering,
  gated pipelines, pool inheritance. Simple cases belong in unit tests.
- **Factory-composed**: All data built from FactoryBoy factories. The same composition patterns
  serve as seed data for integration tests and as templates for unit test setup.
- **Mocked checks**: `perform_check()` is mocked to control outcome tiers. The check system has
  its own tests. Unmocked smoke tests are a future addition.
- **Layerable**: As new systems come online (cooperative actions, equipment sources, discovery
  mechanics), new test methods and assertions get added to these classes.

## File Location

`src/world/mechanics/tests/test_pipeline_integration.py`

Mechanics owns the convergence point — `resolve_challenge()`, `get_available_actions()`,
and the Property/Application/Challenge models that sit at the center of both paths.

## Shared Test Data

Both test classes share a single realistic character setup via a common mixin or base class
with `setUpTestData`. This mirrors how a real character would have one technique usable in
multiple contexts.

### Character

- `ObjectDB` character with a `CharacterSheet`
- Real trait values (e.g., Willpower, Presence) via `CharacterTraitValue` so check types have
  weights to resolve against
- `CharacterGift` and `CharacterTechnique` ownership records

### Magic Identity

- **Affinity**: "Primal"
- **Resonances**: "Flame" (Primal) and "Heat" (Primal)
- **Gift**: "Pyromancy" with both resonances attached
  - These resonances match Property names, enabling effect property resolution
- **Technique**: "Flame Lance"
  - intensity=10, control=7
  - TechniqueStyle with allowed paths
  - At least one Restriction (e.g., "Touch Range") for power bonus
  - FK to Gift ("Pyromancy")

### Multiple Capability Grants

The technique grants two capabilities with different characteristics:

| Grant | Capability | base_value | intensity_multiplier | Effective Value | Prerequisite |
|-------|-----------|------------|---------------------|----------------|--------------|
| 1 | generation | 5 | 1.0 | 15 | None (anyone with the technique can generate fire) |
| 2 | control | 2 | 0.5 | 7 | PrerequisiteType("has_primal_affinity") — represents precision skill |

### Properties and Applications

Effect property resolution works by matching Gift resonance names to Property names
(case-insensitive). Resonance "Flame" lowercased = "flame", so the Property must be
named "flame" (not "flammable"). This is how the system determines what *kind* of
fire a technique produces.

| Property | Category | Purpose | Matches Resonance |
|----------|----------|---------|-------------------|
| flame | elemental | Effect property — "this source produces flame" | "Flame" (exact match) |
| heat | elemental | Effect property — "this source produces heat" | "Heat" (exact match) |
| flammable | elemental | Target property — "this target can be burned" | N/A (challenge property) |

| Application | Capability | Target Property | required_effect_property |
|-------------|-----------|----------------|------------------------|
| Ignite | generation | flammable | None |
| Heat Manipulation | control | flammable | heat (only sources with heat effect properties qualify) |

Note: Both applications target the "flammable" property on challenges. The distinction
is that Heat Manipulation additionally requires the source to have the "heat" effect
property, filtering out sources that produce flame but not directed heat.

### Check Infrastructure

- **CheckType** with trait weights pointing to the character's real traits
- **CheckOutcome** for success (success_level=1) and failure (success_level=-1)
- **Consequences**:
  - Success consequence with two ConsequenceEffects:
    - APPLY_CONDITION ("Burning" ConditionTemplate, severity=3, target=SELF)
    - REMOVE_PROPERTY (removes "flammable" — the thing burned away)
  - Failure consequence with no effects (narrative only)

## Path 1: Challenge Resolution Tests

### Additional Setup

- **ChallengeTemplate** ("Wooden Barricade"):
  - severity=5
  - `flammable` (value=5) as template property (this is the target property that Applications match against)
  - ChallengeTemplateConsequences for success (resolution_type=DESTROY) and failure (PERSONAL)
- **Two ChallengeApproaches**:
  - "Burn Through" — via Ignite application + check type
  - "Heat Warp" — via Heat Manipulation application + check type
  - Both target the same "flammable" property on the challenge, but via different capabilities
- **ChallengeInstance** at a location (ObjectDB room), is_active=True, is_revealed=True

### Test Methods

#### test_capability_sources_returns_both_grants
Call `get_capability_sources_for_character(character)`. Assert:
- Two TECHNIQUE sources returned
- generation source has value=15, correct effect_property_ids (flame + heat from resonances)
- control source has value=7, has prerequisite_id set

#### test_available_actions_returns_both_approaches
Call `get_available_actions(character, location)`. Assert:
- Two AvailableAction entries returned (one per approach)
- Both reference the same challenge instance
- Each has the correct application, approach, and capability source
- Difficulty indicators are populated

#### test_effect_property_filtering_on_heat_manipulation
The Heat Manipulation application has `required_effect_property=heat`. Assert that
`get_available_actions()` only returns it when the capability source's effect_property_ids
include the "heat" property ID. This is satisfied because the Gift has "Heat" resonance
which matches the "heat" Property name (case-insensitive).

#### test_missing_effect_property_excludes_approach
Create a second technique in a Gift that has "Flame" resonance but NOT "Heat". This
technique grants the `control` capability but lacks the "heat" effect property. Assert
that `get_available_actions()` returns the Ignite approach for this technique but NOT
the Heat Manipulation approach (because `required_effect_property=heat` is not satisfied).

#### test_duplicate_resolution_prevented
After resolving a challenge, attempt to resolve it again with the same character. Assert
that `resolve_challenge()` raises `ChallengeResolutionError` because a
CharacterChallengeRecord already exists.

#### test_resolve_challenge_via_ignite_success
Mock `perform_check` to return success outcome. Call `resolve_challenge()` with the
Burn Through approach. Assert:
- Success consequence selected
- ConsequenceEffects applied (condition created, property removed)
- Challenge instance deactivated (DESTROY resolution type)
- CharacterChallengeRecord created

#### test_resolve_challenge_via_heat_warp_success
Same as above but via the Heat Warp approach. Proves both approaches resolve correctly
through the same pipeline.

#### test_resolve_challenge_failure_keeps_challenge_active
Mock `perform_check` to return failure outcome. Assert:
- Failure consequence selected
- No effects applied
- Challenge remains active (PERSONAL resolution type)
- CharacterChallengeRecord still created

## Path 2: Scene Action Resolution Tests

### Current State of Scene Actions

`respond_to_action_request()` → `resolve_scene_action()` is a simpler path than challenge
resolution. It calls `perform_check()` directly and returns a `SceneActionResult` with
pass/fail + outcome name. It does NOT use consequence pools, gated pipelines, or
`start_action_resolution()`. The result is recorded as an Interaction in the scene.

This means Path 2 tests are currently lighter than Path 1 — but they prove the full
consent → resolution → interaction recording flow that players experience. As scene
actions gain consequence pools and effects, tests will grow to match.

### Additional Setup

- **ActionTemplate** ("Intimidating Flames"):
  - pipeline=SINGLE
  - check_type = shared check type (same as challenge path)
  - consequence_pool = None (not used by current resolve_scene_action)
- **Technique.action_template** FK set to the ActionTemplate
- **Scene** at a location with ACTIVE status
- **Two Personas** (initiator = our fire mage, target = another character)
- **Second character** with CharacterSheet for the target persona

### Test Methods

#### test_scene_action_request_consent_flow
Create a SceneActionRequest via the scene action services. Assert:
- Request created in PENDING status
- Links to correct ActionTemplate and Technique
- Initiator and target personas correctly set

#### test_scene_action_accept_resolves_check
Mock `perform_check` to return success outcome. Call `respond_to_action_request()`
with ACCEPT. Assert:
- SceneActionResult returned with success=True
- Result contains correct action_key and check_outcome name
- ActionRequest status transitions: PENDING → ACCEPTED → RESOLVED

#### test_scene_action_deny_returns_none
Call `respond_to_action_request()` with DENY. Assert:
- Returns None
- ActionRequest status = DENIED
- No check performed (perform_check not called)
- No Interaction created

#### test_scene_action_creates_result_interaction
Mock check to return success. After resolution, assert:
- An Interaction record exists in the scene
- Interaction content includes initiator name, action key, and outcome
- Interaction mode is "action"

#### test_scene_action_failure_still_records
Mock check to return failure outcome. Assert:
- SceneActionResult has success=False
- Result interaction still created (the attempt is recorded regardless)
- ActionRequest still marked RESOLVED

#### test_technique_links_through_action_template
Verify the full chain: Technique.action_template → ActionTemplate.check_type → perform_check.
Assert that the check type used in resolution matches the one on the technique's action template.

### Path 2.5: Gated Pipeline via start_action_resolution (Separate Test Class)

`start_action_resolution()` is the more sophisticated action resolution path, currently
entered via `_resolve_via_template()` in challenge resolution (when a ChallengeApproach
has an action_template FK). This deserves its own test class to prove the gated pipeline
and consequence pool inheritance work.

#### Additional Setup

- **ConsequencePool** hierarchy:
  - Parent pool ("Generic Social") with success/failure consequences
  - Child pool ("Flame Intimidation") that inherits from parent, overrides success weight,
    and adds a fire-specific consequence
- **ActionTemplate** ("Flame Intimidation Template"):
  - pipeline=GATED
  - check_type = shared check type
  - consequence_pool = child pool
- **ActionTemplateGate**:
  - gate_role=ACTIVATION
  - Its own check_type and consequence_pool
  - failure_aborts=True

#### Test Methods

##### test_gate_failure_aborts_main_step
Mock gate check to return failure. Call `start_action_resolution()`. Assert:
- Gate consequence applied from gate's pool
- Main step never executed (no main result in PendingActionResolution)
- Phase reaches COMPLETE

##### test_gate_success_proceeds_to_main
Mock gate check to return success, main check to return success. Assert:
- Gate passed
- Main step executed with consequence from child pool
- Pool inheritance resolved correctly (child overrides applied)
- Phase reaches COMPLETE

##### test_pool_inheritance_resolves_correctly
Verify that `get_effective_consequences()` for the child pool includes parent entries
with child overrides applied and any exclusions honored.

## Test Structure

Three test classes in one file:

1. **`ChallengePathTests`** — Challenge discovery and resolution via get_available_actions + resolve_challenge
2. **`SceneActionPathTests`** — Consent flow and simple check resolution via respond_to_action_request
3. **`GatedPipelineTests`** — Gated action resolution via start_action_resolution with pool inheritance

All three share the base character/magic/check setup via a mixin. Each adds its
own domain-specific setup.

## Factory Composition Pattern

The shared setup demonstrates the canonical composition order:

```
1. Character layer:     ObjectDB → CharacterSheet → CharacterTraitValue
2. Magic identity:      Affinity → Resonance → Gift → Technique → TechniqueCapabilityGrant
3. Ownership:           CharacterGift, CharacterTechnique
4. Mechanics layer:     PropertyCategory → Property, CapabilityType → Application
5. Check layer:         CheckCategory → CheckType → CheckOutcome → Consequence → ConsequenceEffect
6. Challenge layer:     ChallengeTemplate → ChallengeTemplateProperty, ChallengeApproach
7. Action layer:        ConsequencePool → ActionTemplate → ActionTemplateGate
8. Scene layer:         Scene → Persona → SceneActionRequest
```

Each layer builds on the previous. This ordering should be followed when composing
factories for any test that touches the pipeline.

## Known Divergences and Design Notes

- **Prerequisite gating is not enforced**: The control grant has a PrerequisiteType but
  `get_available_actions()` does not check prerequisites — it only checks effect property
  requirements. Tests assert the prerequisite_id is populated on the CapabilitySource but
  do not assert it gates availability. This becomes a real test once the prerequisite
  registry (Phase 2) is implemented.
- **capability_source parameter unused in resolve_challenge()**: Passed but marked ARG001.
  Tests pass it for signature correctness but don't assert it affects resolution. Future
  work may use it for difficulty scaling or damage calculation.
- **Scene actions lack consequence application**: `resolve_scene_action()` returns pass/fail
  but does not select or apply consequences. This is the biggest gap between the two paths.

## Future Expansion Points

As systems come online, add test methods for:
- **Prerequisite registry**: Once callables are registered, assert that the control capability's
  prerequisite actually gates availability
- **Cooperative actions**: Multiple characters addressing the same challenge
- **Equipment sources**: A fourth capability source type alongside techniques, traits, conditions
- **Discovery mechanics**: Hidden challenges becoming revealed
- **Situation lifecycle**: SituationInstance with dependent challenges
- **Reroll/negation**: Intervention between consequence selection and application
- **Condition-granted capabilities**: Active conditions providing capability sources
- **Trait-derived capabilities**: TraitCapabilityDerivation providing baseline capabilities
