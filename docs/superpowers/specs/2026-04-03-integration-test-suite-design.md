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
    checks.py        # CheckContent — wraps existing checks.factories helpers; future combat/exploration types
    conditions.py    # ConditionContent — condition categories and named condition templates
    social.py        # SocialContent — consequence pools wired to social action templates
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
Don't block Phase 7 on it.

## Existing Factory Helpers

`world/checks/factories.py` already contains two module-level functions that create the social
action infrastructure with `get_or_create` semantics and correct canonical stat names:

- **`create_social_check_types()`** — creates the Social `CheckCategory`, 6 `CheckType` records,
  and `CheckTypeTrait` wiring using real stat names (presence, strength, charm, intellect, wits,
  willpower). Returns `dict[str, CheckType]` keyed by check type name.
- **`create_social_action_templates()`** — calls the above, then creates 6 `ActionTemplate`
  records with `category="social"` and `consequence_pool=None`. Returns `list[ActionTemplate]`.

The canonical social action data defined there:

| Template name | Check type  | Action key (name.lower()) | Target type |
|---------------|-------------|---------------------------|-------------|
| Intimidate    | Intimidation| intimidate                | single      |
| Persuade      | Persuasion  | persuade                  | single      |
| Deceive       | Deception   | deceive                   | single      |
| Flirt         | Seduction   | flirt                     | single      |
| Perform       | Performance | perform                   | area        |
| Entrance      | Presence    | entrance                  | area        |

**The `game_content/` builders do not reimplement this.** They call these functions directly.
`SocialContent.create_all()` calls `create_social_action_templates()` to obtain the 6 templates,
then adds consequence pools to them.

## Content Builder Design

Each module in `game_content/` is a class with `@classmethod` methods. They import from
app-level `factories.py` files and call them with realistic names and values. They compose:
`SocialContent.create_all()` calls `ConditionContent` internally and wraps
`create_social_action_templates()` from `checks.factories`.

Methods return model instances directly — no intermediate dataclasses.

### `checks.py` — CheckContent

Thin wrapper around the existing `checks.factories` helpers. Exists as the home for future
check type builders (combat, exploration) as those systems come online.

```python
from world.checks.factories import create_social_action_templates, create_social_check_types

class CheckContent:
    @classmethod
    def create_social_check_types(cls) -> dict[str, CheckType]:
        """Delegate to checks.factories.create_social_check_types()."""
        return create_social_check_types()

    @classmethod
    def create_social_action_templates(cls) -> list[ActionTemplate]:
        """Delegate to checks.factories.create_social_action_templates().
        Templates are created with consequence_pool=None; SocialContent adds pools.
        """
        return create_social_action_templates()
```

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

        Returns dict keyed by primary action name:
          "intimidate" -> Shaken   (confidence broken)
          "persuade"   -> Charmed  (socially disarmed)
          "deceive"    -> Deceived (believes a falsehood)
          "flirt"      -> Smitten  (romantically affected)
          "perform"    -> Captivated (absorbed in performance)
          "entrance"   -> Enthralled (overwhelmed by presence)

        All use DurationType.ROUNDS, default_duration_value=3, can_be_dispelled=True.
        """
```

### `social.py` — SocialContent

Orchestrates consequence pools and wires them onto the existing action templates.

```python
class SocialContent:
    ACTION_KEYS = ["intimidate", "persuade", "deceive", "flirt", "perform", "entrance"]

    @classmethod
    def create_consequence_pool(
        cls,
        action_key: str,
        condition: ConditionTemplate,
        outcomes: dict[str, CheckOutcome],
    ) -> ConsequencePool:
        """Build a pool with success/failure/partial consequences.

        Success consequence (weight=2):  APPLY_CONDITION effect → condition.
        Partial consequence (weight=1):  no effect, narrative only.
        Failure consequence (weight=1):  no effect, narrative only.
        Character loss is False for all social consequences.

        Uses CheckOutcome instances from the traits app check system
        (success_level >= 1 = success, 0 = partial, < 0 = failure).
        """

    @classmethod
    def create_all(cls) -> dict[str, ActionTemplate]:
        """Create all social action infrastructure and return templates keyed by action key.

        Calls checks.factories.create_social_action_templates() to create the 6 templates
        (with consequence_pool=None), then creates conditions and consequence pools, and
        updates each template's consequence_pool FK.

        The dict key is template.name.lower() — matching how get_available_scene_actions()
        derives action keys at runtime.

        Returns:
          {"intimidate": <ActionTemplate>, "persuade": <ActionTemplate>, ...}
        """
```

### `characters.py` — CharacterContent

Full character assembly. Composes all other builders.

```python
class CharacterContent:
    @classmethod
    def create_base_social_character(cls) -> tuple[ObjectDB, Persona]:
        """Sheet + trait values for social stats:
          presence=70, charm=60, intellect=50, wits=40, strength=30, willpower=30
          (internal 1-100 scale; display scale is /10)
        No magic. Suitable for testing mundane social action path.

        Also creates a Persona (PRIMARY type) for use in consent flow tests.
        Returns (character ObjectDB, Persona).
        """

    @classmethod
    def create_social_mage(cls) -> tuple[ObjectDB, Persona]:
        """Extends base_social_character with:
        - CharacterAnima (current=50, maximum=50)
        - Fire technique (via MagicContent.create_fire_technique)
        - ActionEnhancement for intimidate and persuade
        Suitable for testing enhanced social action path.
        Returns (character ObjectDB, Persona).
        """
```

`create_base_social_character()` returns a `Persona` alongside the `ObjectDB` because the
consent flow API (`create_action_request`) requires `Persona` instances, and `PersonaFactory`
must be called with the correct `character_identity__character` linkage. Bundling this avoids
each test class independently re-creating the Persona relationship.

### `magic.py` — MagicContent

Technique enhancements for social actions. Pass 2 deliverable — not built in this PR.

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

## Integration Test Structure

### `test_social_pipeline.py` (Phase 7 Pass 1)

All test classes use `setUpTestData`. Check outcomes are made deterministic by mocking
`actions.services.perform_check` (same pattern as `SceneActionPathTests` in
`world/mechanics/tests/test_pipeline_integration.py`).

```
SocialActionAvailabilityTests
  setUpTestData:
    cls.templates = SocialContent.create_all()
    cls.character, cls.persona = CharacterContent.create_base_social_character()
  - get_available_scene_actions(character=cls.character) returns 6 actions
  - each AvailableSceneAction has a non-null action_template with a consequence_pool
  - character with no techniques has empty enhancements list on each action

SocialActionConsentFlowTests
  setUpTestData:
    cls.templates = SocialContent.create_all()
    cls.initiator, cls.initiator_persona = CharacterContent.create_base_social_character()
    cls.target, cls.target_persona = CharacterContent.create_base_social_character()
    cls.scene = SceneFactory()
  - create_action_request → PENDING status, action_template populated from cls.templates["intimidate"]
  - deny → ActionRequestStatus.DENIED, no condition applied to target
  - accept (with mocked perform_check) → ActionRequestStatus.RESOLVED, check performed

  Note: SceneActionRequest.action_template must be set explicitly after create_action_request()
  — the service does not auto-populate it. Tests should set request.action_template and call
  request.save(update_fields=["action_template"]) before calling respond_to_action_request().

SocialActionConsequenceTests
  setUpTestData:
    cls.templates = SocialContent.create_all()
    cls.initiator, cls.initiator_persona = CharacterContent.create_base_social_character()
    cls.target, cls.target_persona = CharacterContent.create_base_social_character()
    cls.scene = SceneFactory()
  Check outcomes controlled via @patch("actions.services.perform_check"):
  - intimidate: mocked success → Shaken condition applied to target
  - intimidate: mocked failure → no condition on target
  - flirt: mocked success → Smitten applied
  - persuade: mocked success → Charmed applied
  - deceive: mocked success → Deceived applied
  - perform: mocked success → Captivated applied
  - entrance: mocked success → Enthralled applied

SocialActionEnhancementTests (Pass 2, same file — not built in this PR)
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
  - high strength trait → force capability via TraitCapabilityDerivation → breakable challenge

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
| `game_content/checks.py` | `CheckContent` — thin wrapper around existing `checks.factories` helpers |
| `game_content/conditions.py` | `ConditionContent` — Social category + 6 named conditions |
| `game_content/social.py` | `SocialContent` — 6 consequence pools, wires pools onto templates |
| `game_content/characters.py` | `CharacterContent.create_base_social_character()` returns `(ObjectDB, Persona)` |
| `integration_tests/pipeline/test_social_pipeline.py` | Availability + consent flow + consequence tests |

**Not in this PR:**
- `magic.py`, `capabilities.py` content builders
- `CharacterContent.create_social_mage()`
- `test_technique_pipeline.py`, `test_capability_pipeline.py`

## Key Constraints

- **No fixtures, no management commands** — all data via FactoryBoy
- **`django_get_or_create` on canonical names** — `CheckCategoryFactory` and
  `ConditionTemplateFactory` use `("name",)`; `CheckTypeFactory` uses `("name", "category")`;
  `StatTraitFactory` uses `("name",)`. All are safe to call from multiple test classes in the
  same run without creating duplicates
- **`setUpTestData` always** — never `setUp` for data that doesn't mutate
- **No cross-test contamination** — no module-level creates, no `get_or_create` outside factory
  `django_get_or_create`; each test class creates its own data via `setUpTestData`
- **Realistic names throughout** — "Intimidation" not "CheckType0", "Smitten" not "Condition1"
- **Deterministic checks** — mock `actions.services.perform_check` for tests that assert
  specific consequence outcomes; do not rely on random roll results in integration tests
