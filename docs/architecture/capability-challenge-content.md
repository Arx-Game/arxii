# Phase 7 Pass 3: Capability & Challenge Seed Content

**Date:** 2026-04-04
**Status:** Approved
**Depends on:** Phase 7 Passes 1 & 2 (social action + technique content builders)

## Goal

Create FactoryBoy-based content builders that populate the Capabilities & Challenges
system with enough seed data to exercise the full pipeline end-to-end: capabilities,
properties, applications, challenges, trait derivations, and technique capability grants.
The same builders serve as both automated integration tests and seed data patterns.

## Architecture Reference

Primary architecture doc: `docs/architecture/property-capability-action.md`

Key principles from that doc that drive this design:
- **Capabilities are atomic primitives** — single-verb names, ~10-15 for physical/magical.
  No compound names like `fire_generation`. The noun (fire, shadow) belongs on the
  **source** as effect Properties, not on the Capability.
- **Applications are pure eligibility** — Capability + Property = "you can attempt this."
  No check type, difficulty, or narrative on the Application itself.
- **Per-source evaluation** — each source of a Capability is a separate Action.
- **~40-60 Applications globally**, 3-8 per Capability.

## Content Design

### CapabilityTypes (19 total)

All created via `CapabilityTypeFactory`. No prerequisites for the starter set.

**Physical/Magical (12) — from architecture doc reference vocabulary:**

| Capability | What it enables |
|---|---|
| `generation` | Creating something from nothing |
| `force` | Raw power — breaking, lifting, pushing, striking |
| `projection` | Directing energy/force at range |
| `manipulation` | Controlling/directing something that already exists |
| `barrier` | Blocking, containing, shielding |
| `traversal` | Moving through/past/over things |
| `movement` | Basic locomotion (baseline human) |
| `precision` | Fine control, accuracy |
| `suppression` | Negating, dampening a quality |
| `transmutation` | Changing one thing into another |
| `communication` | Conveying information across barriers |
| `perception` | Sensing, detecting, analyzing |

**Social (5):**

| Capability | What it enables |
|---|---|
| `intimidation` | Creating fear/compliance |
| `persuasion` | Shifting beliefs/disposition toward agreement |
| `deception` | Creating false beliefs/misperceptions |
| `charm` | Creating emotional attraction/rapport |
| `inspiration` | Uplifting, motivating, energizing |

Social capabilities are distinct primitives because both the means and end states differ —
Fear and Charm are genuinely different conditions, not flavors of the same effect.

**Mental (2):**

| Capability | What it enables |
|---|---|
| `analysis` | Problem-solving, deciphering, understanding mechanisms |
| `exploitation` | Capitalizing on vulnerabilities, surfacing combos |

`exploitation` is distinct from `perception`: Perception detects a vulnerability,
Wits/exploitation determines what to *do* with it — synthesizing party capabilities
into actionable combos. Core to boss fight vulnerability revelation mechanics.

**Not included as capabilities:** Endurance/resistance (passive effects handled by
conditions/modifier system, not things you actively do). Stamina, Composure, Stability,
Willpower, and Luck stats have no capability derivations — they feed fatigue pools
and resistance modifiers instead.

### Properties & PropertyCategories

5 categories, ~27 Properties. Enough to build a meaningful Application matrix.

**Elemental:** flammable, frozen, electrified, flooded, shadowy, radiant, arcane

**Physical:** locked, breakable, heavy, armored, solid, mechanical, enclosed

**Environmental:** dark, underwater, elevated, hazardous, gaseous

**Creature:** abyssal, celestial, undead, bestial, spectral

**Social:** fearful, trusting, proud, reasonable, demoralized

Social Properties describe the social challenge's character, not a vulnerability to a
specific tactic. A "Proud Noble" challenge has `proud` as a Property the same way a
door has `locked` — it's the terrain different social capabilities operate on.

### Applications (~42 total)

Capability + target_property = eligibility. No `required_effect_property` in the
starter set — effect property filtering is tested separately; a technique's effect
properties are its own `Technique.properties` (#5066), never its gift's resonances.

**generation:**
- Ignite — generation + flammable
- Illuminate — generation + dark
- Evaporate — generation + flooded

**force:**
- Break — force + breakable
- Lift — force + heavy
- Breach — force + armored
- Drain — force + flooded

**projection:**
- Blast — projection + solid
- Strike — projection + armored

**manipulation:**
- Channel — manipulation + flooded
- Direct — manipulation + gaseous
- Control — manipulation + mechanical

**barrier:**
- Shield — barrier + hazardous
- Contain — barrier + flooded
- Ward — barrier + arcane
- Block — barrier + armored

**traversal:**
- Navigate — traversal + dark
- Cross — traversal + hazardous
- Escape — traversal + enclosed
- Ascend — traversal + elevated
- Swim — traversal + underwater

**perception:**
- Scout — perception + dark
- Detect — perception + arcane
- Analyze — perception + spectral
- Spot — perception + enclosed

**suppression:**
- Cleanse — suppression + arcane
- Purify — suppression + abyssal
- Dispel — suppression + shadowy
- Exorcise — suppression + undead

**precision:**
- Pick — precision + locked
- Disarm — precision + mechanical

**analysis:**
- Solve — analysis + mechanical
- Decipher — analysis + arcane
- Assess — analysis + armored

**exploitation:**
- Exploit — exploitation + armored
- Shatter — exploitation + breakable

**Social capabilities:**
- Cow — intimidation + proud
- Threaten — intimidation + fearful
- Convince — persuasion + reasonable
- Sway — persuasion + trusting
- Mislead — deception + trusting
- Bluff — deception + proud
- Befriend — charm + reasonable
- Seduce — charm + proud *(placeholder — charm target Property needs redesign)*
- Rally — inspiration + demoralized
- Embolden — inspiration + fearful

`communication`, `transmutation`, and `movement` have no Applications in the starter
set — they'd need Properties not yet defined, and this set is sufficient for pipeline
testing.

### ChallengeCategories

| Category | Description |
|---|---|
| Environmental | Natural hazards, terrain obstacles |
| Physical | Constructed barriers, mechanical obstacles |
| Magical | Arcane wards, enchantments, magical hazards |
| Combat | Hostile creatures, armed opposition |
| Social | Interpersonal obstacles, negotiations, deception |

### CheckTypes for Challenge Approaches

Challenge approaches require a `check_type` FK. Reuse social CheckTypes from Pass 1
where applicable. Create 3 new CheckTypes for non-social approaches:

| CheckType | Primary Trait | Secondary Trait | Used By |
|---|---|---|---|
| physical_challenge | strength | agility | force/barrier approaches |
| magical_challenge | willpower | intellect | generation/suppression/barrier(arcane) approaches |
| precision_challenge | agility | perception | precision/traversal approaches |
| mental_challenge | intellect | wits | analysis/exploitation approaches |
| perception_challenge | perception | wits | perception approaches |

Social approaches on the Proud Noble reuse the existing social CheckTypes from Pass 1
(e.g., intimidate uses the presence-based CheckType, persuade uses the charm-based one).

### Consequence Setup

Each challenge gets a `ConsequencePool` with 4 `Consequence` records (one per outcome
tier). Reuses `CheckOutcome` records from `SocialContent.create_all()` — the builder
depends on social content being created first (same `setUpTestData`).

| Outcome Tier | Label Pattern | Resolution | Effects |
|---|---|---|---|
| failure | "{Challenge} Failure" | No change | None |
| partial | "{Challenge} Partial" | TEMPORARY, 3 rounds | None |
| success | "{Challenge} Success" | DESTROY | None |
| critical | "{Challenge} Critical" | DESTROY | APPLY_CONDITION (bonus) |

The critical tier gets a `ConsequenceEffect` applying a simple condition (e.g.,
"Emboldened" for combat victories, "Enlightened" for magical puzzles). These are
test conditions — 2-3 new `ConditionTemplate` records created by the builder.

`ChallengeTemplateConsequence` through-model records link each consequence to the
template with the resolution_type and duration from the table above.

### Starter Challenges (6 ChallengeTemplates)

**Locked Door** (INHIBITOR, severity 2, category: Physical)
- Properties: locked, solid, breakable
- Approaches:
  - Pick (precision+locked) — precision_challenge
  - Break (force+breakable) — physical_challenge
  - Solve (analysis+mechanical) — mental_challenge
- Note: `mechanical` not on the door itself — Solve approach requires analysis+mechanical
  Application but the door's `locked` Property is what makes it a relevant challenge.
  The approach's Application determines eligibility. This is a deliberate test case for
  "approaches whose Application target_property differs from the Challenge's own Properties."

**Magical Ward** (INHIBITOR, severity 3, category: Magical)
- Properties: arcane, radiant
- Approaches:
  - Cleanse (suppression+arcane) — magical_challenge
  - Decipher (analysis+arcane) — mental_challenge
  - Ward (barrier+arcane) — magical_challenge

**Flooded Chamber** (THREAT, severity 2, category: Environmental)
- Properties: flooded, hazardous, enclosed
- Approaches:
  - Evaporate (generation+flooded) — magical_challenge
  - Drain (force+flooded) — physical_challenge
  - Channel (manipulation+flooded) — magical_challenge
  - Escape (traversal+enclosed) — precision_challenge

**Armored Guardian** (INHIBITOR, severity 4, category: Combat)
- Properties: armored, breakable, bestial
- Approaches:
  - Breach (force+armored) — physical_challenge
  - Assess (analysis+armored) — mental_challenge
  - Exploit (exploitation+armored) — mental_challenge

**Darkness** (INHIBITOR, severity 1, category: Environmental)
- Properties: dark
- Approaches:
  - Illuminate (generation+dark) — magical_challenge
  - Scout (perception+dark) — perception_challenge
  - Navigate (traversal+dark) — precision_challenge

**Proud Noble** (INHIBITOR, severity 2, category: Social)
- Properties: proud, reasonable
- Approaches:
  - Cow (intimidation+proud) — presence CheckType (from Pass 1)
  - Convince (persuasion+reasonable) — charm CheckType (from Pass 1)
  - Bluff (deception+proud) — wits CheckType (from Pass 1)
  - Seduce (charm+proud) — charm CheckType (from Pass 1)

### TraitCapabilityDerivations (11 records)

> **PLACEHOLDER DATA** — these derivations are approximations for pipeline testing.
> Real values will need revision when authored game content defines the actual
> balance between trait-derived and technique-granted capability values.

All use `base_value=0, trait_multiplier=0.5` — a trait value of 50 gives capability
value 25.

| Stat | Capability | Reasoning |
|---|---|---|
| Strength | force | Raw physical power |
| Agility | precision | Coordination, fine control |
| Agility | traversal | Movement, dodging |
| Charm | charm | Emotional attraction |
| Charm | persuasion | Social magnetism applied to argument |
| Charm | deception | Social magnetism applied to misdirection |
| Presence | intimidation | Commanding force of personality |
| Presence | inspiration | Uplifting force of personality |
| Intellect | analysis | Reasoning, problem-solving |
| Wits | exploitation | Tactical synthesis |
| Perception | perception | Awareness, detection |

**Design decision:** Mental stats (Intellect, Wits) do NOT derive social capabilities.
This prevents mental-focused builds from stepping on social-focused builds. Charm owns
persuasion and deception; Presence owns intimidation and inspiration.

**No derivations for:** Stamina, Composure, Stability (endurance stats — feed fatigue
pools, not capabilities), Willpower (meta-stat for all fatigue), Luck (fortune/happenstance).

### TechniqueCapabilityGrants

**Wiring existing social techniques (from Pass 2):**

Each social technique grants 2 social capabilities via `TechniqueCapabilityGrant`.
Uses `base_value=5, intensity_multiplier=1.0` — at intensity 2 (the Pass 2 value),
capability value = 7.

| Technique | Capabilities | Reasoning |
|---|---|---|
| Soul Crush | intimidation, charm | Overwhelming presence — fear and awe |
| Silver Tongue | persuasion, deception | Smooth-talking covers both |
| Veil of Lies | deception, charm | Illusion of what you want to see |
| Heartstring Pull | charm, persuasion | Emotional manipulation |
| Echoing Song | inspiration, charm | Uplifting and captivating |
| Commanding Presence | intimidation, inspiration | Dominating presence: cow or rally |

**New non-social techniques (4, in a new "Elemental Arts" Gift):**

Each grants 2-3 capabilities. Uses `intensity=3, control=3, anima_cost=15`.
Same grant formula: `base_value=5, intensity_multiplier=1.0` → value 8 at intensity 3.

| Technique | Capabilities | Effect Properties |
|---|---|---|
| Flame Lance | generation, force, projection | fire |
| Shadow Step | traversal, perception | shadow |
| Stone Ward | barrier, force | earth/solid |
| Gale Burst | manipulation, projection | air |

Effect Properties are wired via the Resonance system: Gift has M2M to Resonance,
and Resonance has M2M to Property (`Resonance.properties`). The builder creates:
1. Affinity records (reuse existing or create Primal/Celestial/Abyssal via factory)
2. One Resonance per element (fire, shadow, earth, air) with Affinity FK
3. Property records for the effect properties (fire, shadow, earth, air) — these are
   in addition to the target Properties above, as they describe what the *effect* is
   made of, not what the *target* has
4. Wire each Resonance to its Property via M2M
5. Wire each Gift to its Resonances via M2M

Since #5066 (ADR-5066) this no longer gives a technique its effect Properties: a
technique's effect Properties are its own `Technique.properties`, ticked per technique, and
the Gift's resonances never count. Content that needs Flame Lance to carry `fire` ticks
`fire` on the technique itself.

## Content Builder Structure

### New file: `integration_tests/game_content/challenges.py`

`ChallengeContent` class following the Pass 1/2 pattern:

```python
class ChallengeContent:
    @staticmethod
    def create_capability_types() -> dict[str, CapabilityType]: ...

    @staticmethod
    def create_properties() -> dict[str, Property]: ...

    @staticmethod
    def create_applications() -> list[Application]: ...

    @staticmethod
    def create_challenges() -> dict[str, ChallengeTemplate]: ...

    @staticmethod
    def create_trait_derivations() -> list[TraitCapabilityDerivation]: ...

    @staticmethod
    def create_all() -> ChallengeContentResult: ...
```

`ChallengeContentResult` dataclass with: capability_types, properties,
property_categories, applications, challenges, trait_derivations.

### Extend: `integration_tests/game_content/magic.py`

Add to `MagicContent`:
- `create_elemental_techniques()` → 4 new techniques with TechniqueCapabilityGrants
- `wire_social_technique_capabilities(techniques)` → add TechniqueCapabilityGrants
  to existing social techniques
- Update `create_all()` return type to include capability grants

### New file: `integration_tests/pipeline/test_challenge_pipeline.py`

Three test classes:

**`ChallengeAvailabilityTests`** — trait-derived capabilities match challenges
- Character with high Strength sees force-based approaches (Break on Locked Door)
- Character with high Perception sees perception approaches (Scout on Darkness)
- Character with no relevant capabilities sees no approaches

**`TechniqueChallengePipelineTests`** — full technique→capability→application→approach
- Flame Lance character sees Ignite/Illuminate/Evaporate on appropriate challenges
- Shadow Step character sees Navigate on Darkness
- Social technique character sees social approaches on Proud Noble
- Multi-capability technique produces multiple approach options

**`ChallengeResolutionTests`** — end-to-end resolution with consequences
- Successful resolution applies consequence effects, creates CharacterChallengeRecord
- Failed resolution records failure, challenge remains active
- Critical success applies bonus effects (condition grant)

### Character and fixture builder extensions

**`CharacterContent.create_base_challenge_character()`** — new method creating a
character with physical + mental stats (Strength, Agility, Perception, Intellect,
Wits all at value 50) for testing trait→capability derivations against physical
challenges. Includes CharacterSheet, CharacterAnima, and PRIMARY Persona (same
pattern as `create_base_social_character()`).

**Room and object fixtures for ChallengeInstance tests:** `ChallengeInstance` requires
`location` (ObjectDB FK) and `target_object` (ObjectDB FK). The test setup creates:
- A room via Evennia's `create_object()` or `RoomFactory` (the challenge location)
- A target object per challenge (the door, ward, flood, guardian, etc.) via
  `ObjectFactory` or similar — these embody the challenge in the world
- ChallengeInstances linking template → location → target_object

## Implementation Notes

- **Architecture doc update needed:** The reference vocabulary in
  `docs/architecture/property-capability-action.md` lists `endurance` as a Capability
  and does not include social or mental capabilities. Update it to remove `endurance`
  and add the 7 new capabilities (5 social + 2 mental) after this pass lands.
- **Property name divergence:** The architecture doc uses `flooding` where this spec
  uses `flooded`. The spec's names are more consistent (adjective form matching
  `flammable`, `locked`, etc.). The architecture doc examples are illustrative, not
  authoritative — no update needed there.
- **Locked Door approach edge case:** The Solve (analysis+mechanical) approach
  deliberately tests that an approach's Application can reference a Property (`mechanical`)
  not present on the Challenge itself. This validates that approach eligibility comes
  from the Application table, not from Challenge Properties directly.

## Bare-Object Affordances (#2503 addendum)

`Application` gained a nullable `default_template` FK (to `ChallengeTemplate`)
after this pass landed — see `docs/architecture/action-template-pipeline.md`'s
"Bare-Object Affordances" section and ADR-0147. Setting it on an `Application`
row here is what lets `get_available_actions` synthesize a bare-object
affordance (e.g. Ignite on any object carrying `ObjectProperty(flammable)`)
with no authored `ChallengeInstance` placed anywhere. This is opt-in per
Application — the ~42 starter Applications above needed no changes to keep
working exactly as designed; `default_template` only matters for the subset
an author explicitly wants to have ambient world presence outside a
GM-staged Situation. `ChallengeTemplate`/`ChallengeApproach` (the templates
`default_template` points at) are now content-loadable via `CONTENT_MODELS`
(`mechanics.challengetemplate`, `mechanics.challengeapproach`) alongside
`items.itemtemplateproperty` (the template-default-Properties counterpart on
the items side) — the capability-grant content pass (magic-catalog fixtures)
can now author both halves of the bridge.

## What This Does NOT Cover

- `required_effect_property` filtering on Applications (future — needs resonance
  property wiring)
- Cooperative actions (Phase 3 on the roadmap)
- Situation runtime (Phase 5.7)
- Challenge resolution endpoint (Phase 6b)
- Real game-balance tuning of derivation values or technique stats
