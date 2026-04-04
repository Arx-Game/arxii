# Integration Test Suite Architecture & Phase 7 Content

**Date:** 2026-04-03
**Status:** Approved
**Related roadmap:** `docs/roadmap/capabilities-and-challenges.md` Phase 7

## Problem

Every system built so far (social actions, technique enhancements, consequence pools, challenge
resolution) has zero authored game content. A player logging in sees empty action panels. The
pipeline is wired but there is nothing to run through it.

The fix is not fixtures or management commands — it is a **continually expanding integration test
suite** where all game content is created through FactoryBoy factories with realistic names and
values. These factories serve dual purpose: automated integration testing and local dev data for
manual testing.

## Goals

1. A playable social action demo (6 actions with consequences, technique enhancement)
2. An integration test suite architecture that scales as new systems come online
3. One source of truth for "what realistic game content looks like" — shared across all test files
4. No dataclass wrappers, no fixtures, no management commands

## Package Structure

```
src/integration_tests/
  game_content/
    __init__.py
    checks.py        # CheckContent — categories, check types, trait wiring, outcomes, result charts
    conditions.py    # ConditionContent — condition categories and named condition templates
    social.py        # SocialContent — action templates, consequence pools, social conditions
    magic.py         # MagicContent — resonances, gifts, techniques, capability grants, enhancements
    capabilities.py  # CapabilityContent — properties, capability types, applications, derivations
    characters.py    # CharacterContent — full character assembly (sheet, traits, anima, techniques)
  pipeline/
    __init__.py
    test_social_pipeline.py      # Phase 7 Pass 1 deliverable
    # test_technique_pipeline.py  — future: replaces/absorbs world/mechanics/tests/test_pipeline_integration.py
    # test_capability_pipeline.py — future: Phase 6b coverage
  QUICKSTART.md   (existing, untouched)
```

### Note on `test_pipeline_integration.py`

`world/mechanics/tests/test_pipeline_integration.py` stays in place for this PR. When
`test_technique_pipeline.py` is created, the mechanics file can be moved or consolidated.
The user is indifferent to the timing — don't block Phase 7 on it.

## Content Builder Design

Each module in `game_content/` is a class with `@classmethod` methods. They import from
app-level `factories.py` files and call them with realistic names and values. They compose:
`SocialContent.create_all()` calls `CheckContent` and `ConditionContent` internally.
Methods return model instances directly — no intermediate dataclasses.

### `checks.py` — CheckContent

Foundation for everything else. All other content builders depend on it.

```python
class CheckContent:
    @classmethod
    def create_social_category(cls) -> CheckCategory:
        return CheckCategoryFactory(name="Social", display_order=10)

    @classmethod
    def create_social_check_types(cls, category: CheckCategory) -> dict[str, CheckType]:
        """Create one CheckType per social action, wired to appropriate traits.

        Returns dict keyed by action name:
          "intimidate" -> CheckType(name="Intimidation") wired to Presence + Cunning
          "persuade"   -> CheckType(name="Persuasion") wired to Charm + Cunning
          "deceive"    -> CheckType(name="Deception") wired to Cunning + Wits
          "flirt"      -> CheckType(name="Flirtation") wired to Charm + Presence
          "perform"    -> CheckType(name="Performance") wired to Charm + Presence
          "entrance"   -> CheckType(name="Entrance") wired to Presence + Charm
        Each uses CheckTypeTrait to wire traits with appropriate weights.
        """
```

The `create_social_check_types` method creates the traits it needs (Presence, Charm, Cunning,
Wits) via `get_or_create` semantics using `django_get_or_create` on the TraitFactory — these
are canonical stat names that should not be duplicated.

### `conditions.py` — ConditionContent

Social conditions and eventually combat/environmental ones.

```python
class ConditionContent:
    @classmethod
    def create_social_category(cls) -> ConditionCategory:
        return ConditionCategoryFactory(name="Social")

    @classmethod
    def create_social_conditions(cls, category: ConditionCategory) -> dict[str, ConditionTemplate]:
        """Create the 6 social outcome conditions.

        Returns dict:
          "smitten"     -> target is romantically affected (flirt success)
          "shaken"      -> target's confidence is broken (intimidate success)
          "charmed"     -> target is socially disarmed (persuade/entrance success)
          "deceived"    -> target believes a falsehood (deceive success)
          "captivated"  -> target is absorbed in performance (perform success)
          "enthralled"  -> target is overwhelmed by presence (entrance critical)

        All use DurationType.ROUNDS, default_duration_value=3, can_be_dispelled=True.
        """
```

### `social.py` — SocialContent

Orchestrates the full social action stack.

```python
class SocialContent:
    ACTION_KEYS = ["intimidate", "persuade", "deceive", "flirt", "perform", "entrance"]

    @classmethod
    def create_consequence_pool(
        cls,
        action_key: str,
        conditions: dict[str, ConditionTemplate],
        outcomes: dict[str, CheckOutcome],
    ) -> ConsequencePool:
        """Build a pool with success/failure/partial consequences.

        Success consequence: APPLY_CONDITION effect using the primary condition.
        Failure consequence: no effect (narrative only), weight=1.
        Partial consequence: no condition, narrative only.
        Character loss is False for all social consequences.
        """

    @classmethod
    def create_all(cls) -> dict[str, ActionTemplate]:
        """Orchestrate: check category → check types → condition category →
        conditions → check outcomes → consequence pools → action templates.

        Returns dict keyed by action_key:
          {"intimidate": <ActionTemplate>, "persuade": <ActionTemplate>, ...}

        Each ActionTemplate has:
          name = action_key.capitalize()   (so name.lower() == action_key)
          category = "social"
          check_type = matching CheckType
          consequence_pool = matching ConsequencePool
          pipeline = Pipeline.SINGLE
          target_type = ActionTargetType.SINGLE
        """
```

### `magic.py` — MagicContent

Technique enhancements for social actions. Pass 2 deliverable.

```python
class MagicContent:
    @classmethod
    def create_fire_technique(cls, character: ObjectDB) -> Technique:
        """Realistic fire magic technique with:
        - Two TechniqueCapabilityGrants (fire_generation, fire_control)
        - Realistic anima_cost (5)
        - Linked to fire Resonance
        Returns the Technique (CharacterTechnique created as side effect).
        """

    @classmethod
    def create_social_enhancement(
        cls,
        technique: Technique,
        action_key: str,
    ) -> ActionEnhancement:
        """Link a technique to a social action key via ActionEnhancement.

        source_type = EnhancementSourceType.TECHNIQUE
        base_action_key = action_key
        variant_name = f"{technique.name} {action_key.capitalize()}"
        """
```

### `characters.py` — CharacterContent

Full character assembly. Composes all other builders.

```python
class CharacterContent:
    @classmethod
    def create_base_social_character(cls) -> ObjectDB:
        """Sheet + trait values for social stats (Presence 7, Charm 6, Cunning 5, Wits 4).
        No magic. Suitable for testing mundane social action path.
        Returns the character ObjectDB.
        """

    @classmethod
    def create_social_mage(cls) -> ObjectDB:
        """Extends base_social_character with:
        - CharacterAnima (current=50, maximum=50)
        - Fire technique (via MagicContent.create_fire_technique)
        - ActionEnhancement for intimidate and persuade
        Suitable for testing enhanced social action path.
        Returns the character ObjectDB.
        """
```

## Integration Test Structure

### `test_social_pipeline.py` (Phase 7 Pass 1)

```
SocialActionAvailabilityTests
  setUpTestData: SocialContent.create_all() + CharacterContent.create_base_social_character()
  - all 6 action templates returned by get_available_scene_actions()
  - templates have correct check_types and consequence_pools
  - character with no techniques sees no enhancements

SocialActionConsentFlowTests
  setUpTestData: SocialContent.create_all() + two characters (initiator, target) + scene
  - create_action_request → PENDING status
  - deny → ActionRequestStatus.DENIED, no check, no condition applied
  - accept → ActionRequestStatus.RESOLVED, check performed

SocialActionConsequenceTests
  setUpTestData: SocialContent.create_all() + characters + scene
  One test class per action, or parameterized:
  - intimidate success → Shaken condition applied to target
  - intimidate failure → no condition on target
  - flirt success → Smitten condition applied
  - persuade success → Charmed condition applied
  (Covers each of the 6 social conditions)

SocialActionEnhancementTests (Pass 2, same file)
  setUpTestData: above + CharacterContent.create_social_mage()
  - enhanced intimidate → anima deducted + Shaken applied
  - enhanced persuade → soulfray warning surfaced when applicable
  - technique not known → ValidationError on create_action_request
```

### Future pipeline files

**`test_technique_pipeline.py`** (future PR):
- Absorbs `world/mechanics/tests/test_pipeline_integration.py`
- Refactored to use `CharacterContent` and `MagicContent` builders
- Retains all existing test coverage, just with realistic data

**`test_capability_pipeline.py`** (Phase 6b):
```
CapabilityAvailabilityTests
  - fire technique → fire_generation capability → flammable challenge approachable
  - high Strength trait → force capability via TraitCapabilityDerivation → breakable challenge

TraitCapabilityDerivationTests
  - base_value + (multiplier * trait_value) math
  - multiple sources don't aggregate (per-source entries)
```

## Phase 7 Deliverable: Pass 1 Scope

This PR builds Pass 1 only. Pass 2 (technique enhancements) and Pass 3 (capabilities) are
separate PRs.

**What gets built:**

| Component | Detail |
|-----------|--------|
| `game_content/checks.py` | Social check category, 6 check types, trait wiring |
| `game_content/conditions.py` | Social condition category, 6 conditions |
| `game_content/social.py` | 6 consequence pools, 6 ActionTemplates |
| `game_content/characters.py` | `create_base_social_character()` only |
| `integration_tests/pipeline/test_social_pipeline.py` | Availability + consent flow + consequence tests |

**Not in this PR:**
- `magic.py`, `capabilities.py` content builders
- `CharacterContent.create_social_mage()`
- `test_technique_pipeline.py`, `test_capability_pipeline.py`

## Key Constraints

- **No fixtures, no management commands** — all data via FactoryBoy
- **`django_get_or_create` on canonical names** — Trait names (Presence, Charm, etc.) and
  CheckCategory names must not be duplicated across test classes; factories use
  `django_get_or_create = ("name",)` which is already in place for most lookup tables
- **`setUpTestData` always** — never `setUp` for data that doesn't mutate
- **No cross-test contamination** — each test class creates its own data; no module-level
  globals or `get_or_create` outside of factory `django_get_or_create`
- **Realistic names throughout** — "Intimidation" not "CheckType0", "Smitten" not "Condition1"
