# Phase 7 Pass 1 — Social Action Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `game_content/` content builder package and `test_social_pipeline.py` integration tests so the 6 social actions (intimidate, persuade, deceive, flirt, perform, entrance) have consequence pools, conditions, and end-to-end test coverage.

**Architecture:** Centralized content builders in `src/integration_tests/game_content/` call existing app factories with realistic names to create game content. `SocialContent.create_all()` is the top-level orchestrator that wires CheckTypes → Conditions → ConsequencePools → ActionTemplates. A prerequisite change adds `EffectTarget.TARGET` so conditions can be applied to the social action's target character rather than the initiator.

**Tech Stack:** Django TestCase, FactoryBoy, `unittest.mock.patch`, existing app factories (checks, conditions, actions, traits, scenes, character_sheets).

**Spec:** `docs/superpowers/specs/2026-04-03-integration-test-suite-design.md`

---

## File Map

**Create:**
- `src/integration_tests/game_content/__init__.py`
- `src/integration_tests/game_content/checks.py`
- `src/integration_tests/game_content/conditions.py`
- `src/integration_tests/game_content/social.py`
- `src/integration_tests/game_content/characters.py`
- `src/integration_tests/pipeline/__init__.py`
- `src/integration_tests/pipeline/test_social_pipeline.py`

**Modify:**
- `src/world/checks/constants.py` — add `EffectTarget.TARGET`
- `src/world/checks/types.py` — add `target: ObjectDB | None = None` to `ResolutionContext`
- `src/world/mechanics/effect_handlers.py` — handle `EffectTarget.TARGET` in `_resolve_target`
- `src/world/scenes/action_services.py` — pass `target` into `ResolutionContext`

**Migration:** `src/world/checks/migrations/` — cosmetic choices change for `ConsequenceEffect.target`

---

## Task 1: Create package directories and verify test discovery

**Files:**
- Create: `src/integration_tests/game_content/__init__.py`
- Create: `src/integration_tests/pipeline/__init__.py`

- [ ] **Step 1: Create the empty packages**

```bash
# Both files are empty __init__.py
```

Create `src/integration_tests/game_content/__init__.py` — empty file.

Create `src/integration_tests/pipeline/__init__.py` — empty file.

- [ ] **Step 2: Verify test discovery works**

Create a temporary test to confirm the runner finds it:

In `src/integration_tests/pipeline/__init__.py` (or a temporary test file — remove after verifying):

```python
# Temporary — just to verify discovery. Delete after step 3.
```

Actually just run:
```bash
arx test integration_tests.pipeline
```
Expected: `Ran 0 tests` (no tests yet, but no import errors). If you get `ModuleNotFoundError`, the `integration_tests` package may not be on the path — in that case, check that `src/` is in `PYTHONPATH` (it should be as the Django project root).

- [ ] **Step 3: Commit package scaffolding**

```bash
git checkout -b feature/phase7-social-integration-tests
git add src/integration_tests/game_content/__init__.py src/integration_tests/pipeline/__init__.py
git commit -m "feat: add game_content and pipeline packages for integration tests"
```

---

## Task 2: Add EffectTarget.TARGET support

Social consequences need to apply to the action's **target** (the person being intimidated, flirted with, etc.), not the initiator. Currently `EffectTarget` only has `SELF` and `LOCATION`. This task adds `TARGET` support across 4 files and generates the migration.

**Files:**
- Modify: `src/world/checks/constants.py`
- Modify: `src/world/checks/types.py`
- Modify: `src/world/mechanics/effect_handlers.py`
- Modify: `src/world/scenes/action_services.py`
- Migration: `src/world/checks/migrations/`

- [ ] **Step 1: Write a failing test for _resolve_target with TARGET**

In `src/world/mechanics/tests/test_effect_handlers.py` (check if this file exists; if not, create it in `src/world/mechanics/tests/`):

```python
from unittest.mock import MagicMock
from django.test import TestCase
from world.checks.constants import EffectTarget
from world.mechanics.effect_handlers import _resolve_target


class ResolveTargetTests(TestCase):
    def test_self_returns_context_character(self):
        effect = MagicMock(target=EffectTarget.SELF)
        character = MagicMock()
        context = MagicMock(character=character)
        assert _resolve_target(effect, context) is character

    def test_target_returns_context_target(self):
        effect = MagicMock(target=EffectTarget.TARGET)
        target_char = MagicMock()
        context = MagicMock(target=target_char)
        assert _resolve_target(effect, context) is target_char

    def test_target_falls_back_to_character_when_target_is_none(self):
        effect = MagicMock(target=EffectTarget.TARGET)
        character = MagicMock()
        context = MagicMock(target=None, character=character)
        assert _resolve_target(effect, context) is character
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
arx test world.mechanics.tests.test_effect_handlers
```
Expected: 2 failures (`TARGET` doesn't exist yet, `context.target` doesn't exist yet).

- [ ] **Step 3: Add EffectTarget.TARGET to constants**

In `src/world/checks/constants.py`, find `class EffectTarget` and add `TARGET`:

```python
class EffectTarget(models.TextChoices):
    SELF = "self", "Self (acting character)"
    TARGET = "target", "Target (recipient of social or targeted action)"
    LOCATION = "location", "Location (challenge's room)"
```

- [ ] **Step 4: Add target field to ResolutionContext**

In `src/world/checks/types.py`, add `target` to `ResolutionContext`:

```python
@dataclass
class ResolutionContext:
    """Carries character and typed optional source refs for consequence resolution."""

    character: ObjectDB
    challenge_instance: ChallengeInstance | None = None
    action_context: ActionContext | None = None
    target: ObjectDB | None = None
```

- [ ] **Step 5: Update _resolve_target to handle TARGET**

In `src/world/mechanics/effect_handlers.py`, update `_resolve_target`:

```python
def _resolve_target(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> "ObjectDB":
    """Resolve the target ObjectDB for an effect based on EffectTarget."""
    if effect.target == EffectTarget.TARGET:
        return context.target if context.target is not None else context.character
    if effect.target == EffectTarget.LOCATION:
        return context.location
    return context.character
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
arx test world.mechanics.tests.test_effect_handlers
```
Expected: 3 tests pass.

- [ ] **Step 7: Update respond_to_action_request to pass target into context**

In `src/world/scenes/action_services.py`, find the `ACCEPT` branch in `respond_to_action_request`. Change:

```python
character = action_request.initiator_persona.character
context = ResolutionContext(character=character)
```

To:

```python
character = action_request.initiator_persona.character
target_character = action_request.target_persona.character
context = ResolutionContext(character=character, target=target_character)
```

- [ ] **Step 8: Generate migration for choices change**

```bash
arx manage makemigrations checks --name="add_target_to_effect_target"
```

Expected: A new migration file in `src/world/checks/migrations/`. This is a cosmetic migration (choices don't change DB schema in PostgreSQL). Verify it looks correct — it should modify `ConsequenceEffect.target` field choices only.

- [ ] **Step 9: Apply migration and run existing tests**

```bash
arx manage migrate
arx test world.checks world.mechanics world.scenes --keepdb
```

Expected: All existing tests pass. No regressions.

- [ ] **Step 10: Commit**

```bash
git add src/world/checks/constants.py src/world/checks/types.py \
        src/world/mechanics/effect_handlers.py src/world/scenes/action_services.py \
        src/world/mechanics/tests/test_effect_handlers.py \
        src/world/checks/migrations/
git commit -m "feat: add EffectTarget.TARGET for social action consequence targeting"
```

---

## Task 3: CheckContent — thin wrapper

**Files:**
- Create: `src/integration_tests/game_content/checks.py`

- [ ] **Step 1: Write a failing test for CheckContent**

In `src/integration_tests/pipeline/test_social_pipeline.py` (create the file):

```python
"""Integration tests for the social action pipeline."""

from django.test import TestCase

from integration_tests.game_content.checks import CheckContent
from world.checks.models import CheckCategory, CheckType


class CheckContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.check_types = CheckContent.create_social_check_types()

    def test_creates_social_category(self):
        assert CheckCategory.objects.filter(name="Social").exists()

    def test_creates_six_check_types(self):
        assert len(self.check_types) == 6

    def test_check_types_have_correct_names(self):
        expected = {"Intimidation", "Persuasion", "Deception", "Seduction", "Performance", "Presence"}
        assert set(self.check_types.keys()) == expected

    def test_check_types_have_trait_wiring(self):
        intimidation = self.check_types["Intimidation"]
        assert intimidation.traits.exists()
```

- [ ] **Step 2: Run to confirm failure**

```bash
arx test integration_tests.pipeline.test_social_pipeline
```
Expected: `ImportError` — `CheckContent` doesn't exist yet.

- [ ] **Step 3: Implement CheckContent**

Create `src/integration_tests/game_content/checks.py`:

```python
"""CheckContent — thin wrapper around existing check factory helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.checks.factories import create_social_action_templates, create_social_check_types

if TYPE_CHECKING:
    from actions.models import ActionTemplate
    from world.checks.models import CheckType


class CheckContent:
    """Thin wrapper around world/checks/factories.py social helpers.

    Exists as the future home for combat, exploration, and magic check type
    builders as those systems come online.
    """

    @classmethod
    def create_social_check_types(cls) -> dict[str, CheckType]:
        """Delegate to checks.factories.create_social_check_types().

        Creates the Social CheckCategory, 6 CheckTypes, and trait wiring.
        Safe to call multiple times — uses get_or_create throughout.

        Returns:
            Dict mapping check type name to CheckType instance.
        """
        return create_social_check_types()

    @classmethod
    def create_social_action_templates(cls) -> list[ActionTemplate]:
        """Delegate to checks.factories.create_social_action_templates().

        Creates 6 social ActionTemplates with consequence_pool=None.
        SocialContent.create_all() calls this and then adds pools.
        Safe to call multiple times — uses get_or_create throughout.

        Returns:
            List of ActionTemplate instances (consequence_pool=None).
        """
        return create_social_action_templates()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k CheckContent
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/integration_tests/game_content/checks.py \
        src/integration_tests/pipeline/test_social_pipeline.py
git commit -m "feat: add CheckContent wrapper and initial pipeline test file"
```

---

## Task 4: ConditionContent — 6 named social conditions

**Files:**
- Create: `src/integration_tests/game_content/conditions.py`
- Modify: `src/integration_tests/pipeline/test_social_pipeline.py`

- [ ] **Step 1: Write failing tests for ConditionContent**

Add to `src/integration_tests/pipeline/test_social_pipeline.py`:

```python
from integration_tests.game_content.conditions import ConditionContent
from world.conditions.models import ConditionCategory, ConditionTemplate


class ConditionContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = ConditionContent.create_social_category()
        cls.conditions = ConditionContent.create_social_conditions(cls.category)

    def test_creates_social_category(self):
        assert ConditionCategory.objects.filter(name="Social").exists()

    def test_creates_six_conditions(self):
        assert len(self.conditions) == 6

    def test_all_action_keys_present(self):
        expected = {"intimidate", "persuade", "deceive", "flirt", "perform", "entrance"}
        assert set(self.conditions.keys()) == expected

    def test_conditions_have_correct_names(self):
        assert self.conditions["intimidate"].name == "Shaken"
        assert self.conditions["flirt"].name == "Smitten"
        assert self.conditions["persuade"].name == "Charmed"
        assert self.conditions["deceive"].name == "Deceived"
        assert self.conditions["perform"].name == "Captivated"
        assert self.conditions["entrance"].name == "Enthralled"

    def test_conditions_are_dispellable_with_round_duration(self):
        from world.conditions.constants import DurationType
        for condition in self.conditions.values():
            assert condition.can_be_dispelled is True
            assert condition.default_duration_type == DurationType.ROUNDS
            assert condition.default_duration_value == 3
```

- [ ] **Step 2: Run to confirm failure**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k ConditionContent
```
Expected: `ImportError` — `ConditionContent` doesn't exist yet.

- [ ] **Step 3: Implement ConditionContent**

Create `src/integration_tests/game_content/conditions.py`:

```python
"""ConditionContent — named social (and future combat/environmental) conditions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.constants import DurationType
from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory

if TYPE_CHECKING:
    from world.conditions.models import ConditionCategory, ConditionTemplate

# Maps action key → (condition name, narrative description)
_SOCIAL_CONDITIONS: list[tuple[str, str, str]] = [
    ("intimidate", "Shaken", "Target's confidence is broken by the weight of the threat."),
    ("persuade", "Charmed", "Target is socially disarmed and receptive to the speaker."),
    ("deceive", "Deceived", "Target believes a falsehood presented as truth."),
    ("flirt", "Smitten", "Target is romantically affected and distracted."),
    ("perform", "Captivated", "Target is absorbed in the performance, attention held fast."),
    ("entrance", "Enthralled", "Target is overwhelmed by force of presence."),
]


class ConditionContent:
    """Social condition templates for the 6 core social actions."""

    @classmethod
    def create_social_category(cls) -> ConditionCategory:
        """Create (or get) the Social condition category."""
        return ConditionCategoryFactory(name="Social")

    @classmethod
    def create_social_conditions(
        cls,
        category: ConditionCategory,
    ) -> dict[str, ConditionTemplate]:
        """Create the 6 social outcome conditions.

        Returns:
            Dict keyed by action key (e.g., "intimidate" → Shaken template).
        """
        conditions: dict[str, ConditionTemplate] = {}
        for action_key, name, description in _SOCIAL_CONDITIONS:
            conditions[action_key] = ConditionTemplateFactory(
                name=name,
                category=category,
                description=description,
                default_duration_type=DurationType.ROUNDS,
                default_duration_value=3,
                can_be_dispelled=True,
            )
        return conditions
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k ConditionContent
```
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/integration_tests/game_content/conditions.py \
        src/integration_tests/pipeline/test_social_pipeline.py
git commit -m "feat: add ConditionContent with 6 named social conditions"
```

---

## Task 4b: Add django_get_or_create to CheckOutcomeFactory

`CheckOutcomeFactory` has no `django_get_or_create`. Multiple test classes calling `SocialContent.create_all()` in `setUpTestData` would each create new `CheckOutcome` rows named "Success", "Failure", etc. Tests that then do `CheckOutcome.objects.get(name="Success")` would get `MultipleObjectsReturned`. Fix this before implementing `SocialContent`.

**Files:**
- Modify: `src/world/traits/factories.py`

- [ ] **Step 1: Add django_get_or_create to CheckOutcomeFactory**

In `src/world/traits/factories.py`, find `CheckOutcomeFactory` and update its `Meta`:

```python
class CheckOutcomeFactory(factory_django.DjangoModelFactory):
    """Factory for creating CheckOutcome instances."""

    class Meta:
        model = CheckOutcome
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Outcome_{n}")
    description = factory.Faker("sentence")
    success_level = factory.Faker("random_int", min=-5, max=5)
    display_template = factory.Faker("sentence")
```

- [ ] **Step 2: Run traits tests to confirm no regressions**

```bash
arx test world.traits world.checks --keepdb
```
Expected: All existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/world/traits/factories.py
git commit -m "fix: add django_get_or_create to CheckOutcomeFactory to prevent MultipleObjectsReturned"
```

---

## Task 5: SocialContent — consequence pools and create_all

**Files:**
- Create: `src/integration_tests/game_content/social.py`
- Modify: `src/integration_tests/pipeline/test_social_pipeline.py`

- [ ] **Step 1: Write failing tests for SocialContent**

Add to `src/integration_tests/pipeline/test_social_pipeline.py`:

```python
from integration_tests.game_content.social import SocialContent
from actions.models import ActionTemplate, ConsequencePool
from world.checks.constants import EffectType


class SocialContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.templates = SocialContent.create_all()

    def test_returns_six_templates(self):
        assert len(self.templates) == 6

    def test_all_action_keys_present(self):
        expected = {"intimidate", "persuade", "deceive", "flirt", "perform", "entrance"}
        assert set(self.templates.keys()) == expected

    def test_all_templates_have_consequence_pools(self):
        for key, template in self.templates.items():
            assert template.consequence_pool is not None, f"{key} template missing consequence_pool"

    def test_intimidate_pool_has_apply_condition_on_success(self):
        template = self.templates["intimidate"]
        pool = template.consequence_pool
        # Find success consequence entry
        from actions.models import ConsequencePoolEntry
        success_entries = [
            e for e in pool.entries.all()
            if e.consequence.outcome_tier.success_level >= 1
        ]
        assert len(success_entries) > 0
        success_consequence = success_entries[0].consequence
        # Has APPLY_CONDITION effect
        assert success_consequence.effects.filter(
            effect_type=EffectType.APPLY_CONDITION
        ).exists()

    def test_intimidate_success_condition_is_shaken(self):
        template = self.templates["intimidate"]
        pool = template.consequence_pool
        from actions.models import ConsequencePoolEntry
        success_entries = [
            e for e in pool.entries.select_related("consequence__effects__condition_template").all()
            if e.consequence.outcome_tier.success_level >= 1
        ]
        effect = success_entries[0].consequence.effects.get(
            effect_type=EffectType.APPLY_CONDITION
        )
        assert effect.condition_template.name == "Shaken"

    def test_templates_have_social_category(self):
        for key, template in self.templates.items():
            assert template.category == "social", f"{key} template has wrong category"
```

- [ ] **Step 2: Run to confirm failure**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k SocialContent
```
Expected: `ImportError` — `SocialContent` doesn't exist yet.

- [ ] **Step 3: Implement SocialContent**

Create `src/integration_tests/game_content/social.py`:

```python
"""SocialContent — wires consequence pools onto the 6 social action templates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.factories import ConsequencePoolFactory, ConsequencePoolEntryFactory
from integration_tests.game_content.conditions import ConditionContent
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory, create_social_action_templates
from world.traits.factories import CheckOutcomeFactory

if TYPE_CHECKING:
    from actions.models import ActionTemplate, ConsequencePool
    from world.conditions.models import ConditionTemplate
    from world.traits.models import CheckOutcome

# Maps template name (capitalized) → action key for condition lookup
_TEMPLATE_TO_ACTION_KEY: dict[str, str] = {
    "Intimidate": "intimidate",
    "Persuade": "persuade",
    "Deceive": "deceive",
    "Flirt": "flirt",
    "Perform": "perform",
    "Entrance": "entrance",
}


class SocialContent:
    """Orchestrates social action infrastructure for integration tests.

    Calls the existing checks.factories helpers to create ActionTemplates,
    then adds consequence pools targeting the social action's target character.
    """

    ACTION_KEYS = list(_TEMPLATE_TO_ACTION_KEY.values())

    @classmethod
    def create_all(cls) -> dict[str, ActionTemplate]:
        """Create all social action infrastructure and return templates keyed by action key.

        Orchestration order:
          1. CheckOutcome tiers (for pool entry wiring)
          2. ConditionCategory + social conditions
          3. ActionTemplates via checks.factories (consequence_pool=None)
          4. ConsequencePools wired onto each template

        The dict key is template.name.lower() — how get_available_scene_actions()
        derives action keys at runtime.

        Returns:
            {"intimidate": <ActionTemplate>, "persuade": <ActionTemplate>, ...}
        """
        outcomes = cls._create_check_outcomes()
        condition_category = ConditionContent.create_social_category()
        conditions = ConditionContent.create_social_conditions(condition_category)
        templates = create_social_action_templates()

        result: dict[str, ActionTemplate] = {}
        for template in templates:
            action_key = _TEMPLATE_TO_ACTION_KEY[template.name]
            condition = conditions[action_key]
            pool = cls.create_consequence_pool(action_key, condition, outcomes)
            template.consequence_pool = pool
            template.save(update_fields=["consequence_pool"])
            result[action_key] = template

        return result

    @classmethod
    def create_consequence_pool(
        cls,
        action_key: str,
        condition: ConditionTemplate,
        outcomes: dict[str, CheckOutcome],
    ) -> ConsequencePool:
        """Build a consequence pool for one social action.

        Structure:
          Success (success_level >= 1, weight=2): APPLY_CONDITION on TARGET
          Partial (success_level == 0, weight=1):  no effect, narrative only
          Failure (success_level < 0,  weight=1):  no effect, narrative only

        Effects use EffectTarget.TARGET so the condition applies to the
        social action's target character, not the initiator.
        """
        pool = ConsequencePoolFactory(name=f"{action_key.capitalize()} Pool")

        # Success → apply condition to the target
        success_consequence = ConsequenceFactory(
            outcome_tier=outcomes["success"],
            label=f"{action_key.capitalize()} succeeded",
            weight=2,
            character_loss=False,
        )
        ConsequenceEffectFactory(
            consequence=success_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=condition,
            target=EffectTarget.TARGET,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=success_consequence)

        # Partial → narrative only
        partial_consequence = ConsequenceFactory(
            outcome_tier=outcomes["partial"],
            label=f"{action_key.capitalize()} partial success",
            weight=1,
            character_loss=False,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=partial_consequence)

        # Failure → narrative only
        failure_consequence = ConsequenceFactory(
            outcome_tier=outcomes["failure"],
            label=f"{action_key.capitalize()} failed",
            weight=1,
            character_loss=False,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=failure_consequence)

        return pool

    @classmethod
    def _create_check_outcomes(cls) -> dict[str, CheckOutcome]:
        """Create canonical CheckOutcome tiers for pool consequence wiring.

        These same instances are used when building mock CheckResults in tests:
          CheckOutcome.objects.get(name="Success")

        Returns:
            {"failure": <CheckOutcome>, "partial": <CheckOutcome>, "success": <CheckOutcome>}
        """
        return {
            "failure": CheckOutcomeFactory(name="Failure", success_level=-1),
            "partial": CheckOutcomeFactory(name="Partial Success", success_level=0),
            "success": CheckOutcomeFactory(name="Success", success_level=1),
        }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k SocialContent
```
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/integration_tests/game_content/social.py \
        src/integration_tests/pipeline/test_social_pipeline.py
git commit -m "feat: add SocialContent with consequence pools for all 6 social actions"
```

---

## Task 6: CharacterContent — base social character

**Files:**
- Create: `src/integration_tests/game_content/characters.py`
- Modify: `src/integration_tests/pipeline/test_social_pipeline.py`

- [ ] **Step 1: Write failing tests**

Add to `src/integration_tests/pipeline/test_social_pipeline.py`:

```python
from integration_tests.game_content.characters import CharacterContent
from evennia.objects.models import ObjectDB
from world.scenes.models import Persona
from world.traits.models import CharacterTraitValue


class CharacterContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character, cls.persona = CharacterContent.create_base_social_character("Alice")

    def test_returns_object_db(self):
        assert isinstance(self.character, ObjectDB)

    def test_returns_persona(self):
        assert isinstance(self.persona, Persona)
        assert self.persona.character == self.character

    def test_has_presence_trait(self):
        assert CharacterTraitValue.objects.filter(
            character=self.character,
            trait__name="presence",
            value=70,
        ).exists()

    def test_has_charm_trait(self):
        assert CharacterTraitValue.objects.filter(
            character=self.character,
            trait__name="charm",
            value=60,
        ).exists()
```

- [ ] **Step 2: Run to confirm failure**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k CharacterContent
```
Expected: `ImportError` — `CharacterContent` doesn't exist yet.

- [ ] **Step 3: Implement CharacterContent**

Create `src/integration_tests/game_content/characters.py`:

```python
"""CharacterContent — realistic character assembly for integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.character_sheets.factories import CompleteCharacterFactory
from world.scenes.factories import PersonaFactory
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB
    from world.scenes.models import Persona

# Trait values on the internal 1-100 scale (display is /10)
_SOCIAL_TRAIT_VALUES: dict[str, int] = {
    "presence": 70,
    "charm": 60,
    "intellect": 50,
    "wits": 40,
}


class CharacterContent:
    """Full character assembly for integration tests."""

    @classmethod
    def create_base_social_character(
        cls,
        name: str = "Social Test Character",
    ) -> tuple[ObjectDB, Persona]:
        """Create a character with social trait values and a primary Persona.

        Social traits (internal 1-100 scale):
          presence=70, charm=60, intellect=50, wits=40

        No magic, no anima. Suitable for testing mundane social action path.

        Returns:
            (character ObjectDB, primary Persona for use in consent flow tests)
        """
        data = CompleteCharacterFactory.create(name)
        character: ObjectDB = data["character"]

        for trait_name, value in _SOCIAL_TRAIT_VALUES.items():
            trait = StatTraitFactory(name=trait_name)
            CharacterTraitValueFactory(character=character, trait=trait, value=value)

        persona = PersonaFactory(
            character_identity=data["identity"],
            character=character,
        )
        return character, persona
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k CharacterContent
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/integration_tests/game_content/characters.py \
        src/integration_tests/pipeline/test_social_pipeline.py
git commit -m "feat: add CharacterContent with create_base_social_character"
```

---

## Task 7: SocialActionAvailabilityTests

**Files:**
- Modify: `src/integration_tests/pipeline/test_social_pipeline.py`

- [ ] **Step 1: Write the test class**

Add to `src/integration_tests/pipeline/test_social_pipeline.py`:

```python
from world.scenes.action_availability import get_available_scene_actions


class SocialActionAvailabilityTests(TestCase):
    """get_available_scene_actions returns all 6 social actions with pools."""

    @classmethod
    def setUpTestData(cls):
        cls.action_templates = SocialContent.create_all()
        cls.character, cls.persona = CharacterContent.create_base_social_character("Availability Test")

    def test_returns_six_actions(self):
        actions = get_available_scene_actions(character=self.character)
        assert len(actions) == 6

    def test_all_action_keys_present(self):
        actions = get_available_scene_actions(character=self.character)
        keys = {a.action_key for a in actions}
        expected = {"intimidate", "persuade", "deceive", "flirt", "perform", "entrance"}
        assert keys == expected

    def test_all_templates_have_consequence_pools(self):
        actions = get_available_scene_actions(character=self.character)
        for action in actions:
            assert action.action_template.consequence_pool is not None, (
                f"{action.action_key} action template has no consequence_pool"
            )

    def test_character_with_no_techniques_has_no_enhancements(self):
        actions = get_available_scene_actions(character=self.character)
        for action in actions:
            assert action.enhancements == [], (
                f"{action.action_key} unexpectedly has enhancements"
            )
```

- [ ] **Step 2: Run tests**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k SocialActionAvailability
```
Expected: 4 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/integration_tests/pipeline/test_social_pipeline.py
git commit -m "test: add SocialActionAvailabilityTests"
```

---

## Task 8: SocialActionConsentFlowTests

**Files:**
- Modify: `src/integration_tests/pipeline/test_social_pipeline.py`

- [ ] **Step 1: Write the test class**

Add to `src/integration_tests/pipeline/test_social_pipeline.py`:

```python
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import SceneFactory


class SocialActionConsentFlowTests(TestCase):
    """Consent flow: create_action_request → accept/deny → resolution."""

    @classmethod
    def setUpTestData(cls):
        cls.action_templates = SocialContent.create_all()
        cls.initiator, cls.initiator_persona = CharacterContent.create_base_social_character("Initiator")
        cls.target, cls.target_persona = CharacterContent.create_base_social_character("Target")
        cls.scene = SceneFactory()

    def _make_pending_request(self, action_key: str = "intimidate"):
        """Create a SceneActionRequest with action_template populated."""
        template = self.action_templates[action_key]
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key=action_key,
        )
        # create_action_request does not auto-populate action_template.
        # Must be set explicitly before resolution.
        request.action_template = template
        request.save(update_fields=["action_template"])
        return request

    def test_create_request_is_pending(self):
        request = self._make_pending_request()
        assert request.status == ActionRequestStatus.PENDING
        assert request.action_template == self.action_templates["intimidate"]
        assert request.initiator_persona == self.initiator_persona
        assert request.target_persona == self.target_persona

    def test_deny_sets_denied_status(self):
        request = self._make_pending_request()
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )
        assert result is None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.DENIED

    @patch("actions.services.perform_check")
    def test_accept_resolves_and_sets_resolved_status(self, mock_check):
        from unittest.mock import MagicMock
        from world.traits.models import CheckOutcome
        success_outcome = CheckOutcome.objects.get(name="Success")
        mock_check.return_value = MagicMock(outcome=success_outcome)

        request = self._make_pending_request()
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED

    @patch("actions.services.perform_check")
    def test_accept_returns_enhanced_scene_action_result(self, mock_check):
        from unittest.mock import MagicMock
        from world.scenes.types import EnhancedSceneActionResult
        from world.traits.models import CheckOutcome
        success_outcome = CheckOutcome.objects.get(name="Success")
        mock_check.return_value = MagicMock(outcome=success_outcome)

        request = self._make_pending_request()
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert isinstance(result, EnhancedSceneActionResult)
        assert result.action_key == "intimidate"
        assert result.action_resolution is not None
```

Note: `patch` needs to be imported. Add this import at the top of `test_social_pipeline.py`:
```python
from unittest.mock import MagicMock, patch
```

- [ ] **Step 2: Run tests**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k SocialActionConsent
```
Expected: 4 tests pass. If `CheckOutcome.objects.get(name="Success")` raises `DoesNotExist`, it means `SocialContent.create_all()` isn't in this test class's `setUpTestData`. Check that `cls.action_templates = SocialContent.create_all()` is present — this creates the CheckOutcome records.

- [ ] **Step 3: Commit**

```bash
git add src/integration_tests/pipeline/test_social_pipeline.py
git commit -m "test: add SocialActionConsentFlowTests"
```

---

## Task 9: SocialActionConsequenceTests

Tests that accepted social actions apply the correct conditions to the target.

**Files:**
- Modify: `src/integration_tests/pipeline/test_social_pipeline.py`

- [ ] **Step 1: Write the test class**

Add to `src/integration_tests/pipeline/test_social_pipeline.py`:

```python
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.traits.models import CheckOutcome


class SocialActionConsequenceTests(TestCase):
    """Accepted social actions apply conditions to the target character."""

    @classmethod
    def setUpTestData(cls):
        cls.action_templates = SocialContent.create_all()
        cls.initiator, cls.initiator_persona = CharacterContent.create_base_social_character("ConseqInitiator")
        cls.target, cls.target_persona = CharacterContent.create_base_social_character("ConseqTarget")
        cls.scene = SceneFactory()
        # Retrieve outcomes created by create_all() for mock return values
        cls.success_outcome = CheckOutcome.objects.get(name="Success")
        cls.failure_outcome = CheckOutcome.objects.get(name="Failure")

    def _accept_action(self, action_key: str, outcome: CheckOutcome) -> None:
        """Helper: create request, mock check result, accept, resolve."""
        template = self.action_templates[action_key]
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key=action_key,
        )
        request.action_template = template
        request.save(update_fields=["action_template"])

        with patch("actions.services.perform_check") as mock_check:
            mock_check.return_value = MagicMock(outcome=outcome)
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )

    def test_intimidate_success_applies_shaken_to_target(self):
        self._accept_action("intimidate", self.success_outcome)
        shaken = ConditionTemplate.objects.get(name="Shaken")
        assert ConditionInstance.objects.filter(
            target=self.target,
            condition=shaken,
        ).exists()

    def test_intimidate_failure_no_condition_on_target(self):
        self._accept_action("intimidate", self.failure_outcome)
        shaken = ConditionTemplate.objects.get(name="Shaken")
        assert not ConditionInstance.objects.filter(
            target=self.target,
            condition=shaken,
        ).exists()

    def test_intimidate_success_no_condition_on_initiator(self):
        """Condition goes to target (EffectTarget.TARGET), not initiator."""
        self._accept_action("intimidate", self.success_outcome)
        shaken = ConditionTemplate.objects.get(name="Shaken")
        assert not ConditionInstance.objects.filter(
            target=self.initiator,
            condition=shaken,
        ).exists()

    def test_flirt_success_applies_smitten_to_target(self):
        self._accept_action("flirt", self.success_outcome)
        smitten = ConditionTemplate.objects.get(name="Smitten")
        assert ConditionInstance.objects.filter(
            target=self.target,
            condition=smitten,
        ).exists()

    def test_persuade_success_applies_charmed_to_target(self):
        self._accept_action("persuade", self.success_outcome)
        charmed = ConditionTemplate.objects.get(name="Charmed")
        assert ConditionInstance.objects.filter(
            target=self.target,
            condition=charmed,
        ).exists()

    def test_deceive_success_applies_deceived_to_target(self):
        self._accept_action("deceive", self.success_outcome)
        deceived = ConditionTemplate.objects.get(name="Deceived")
        assert ConditionInstance.objects.filter(
            target=self.target,
            condition=deceived,
        ).exists()

    def test_perform_success_applies_captivated_to_target(self):
        self._accept_action("perform", self.success_outcome)
        captivated = ConditionTemplate.objects.get(name="Captivated")
        assert ConditionInstance.objects.filter(
            target=self.target,
            condition=captivated,
        ).exists()

    def test_entrance_success_applies_enthralled_to_target(self):
        self._accept_action("entrance", self.success_outcome)
        enthralled = ConditionTemplate.objects.get(name="Enthralled")
        assert ConditionInstance.objects.filter(
            target=self.target,
            condition=enthralled,
        ).exists()
```

- [ ] **Step 2: Run tests**

```bash
arx test integration_tests.pipeline.test_social_pipeline -k SocialActionConsequence
```
Expected: 8 tests pass.

If any consequence test fails with `ConditionInstance` not found, check:
1. `EffectTarget.TARGET` is being used in the pool entries (Task 5)
2. `respond_to_action_request` is passing `target` into `ResolutionContext` (Task 2)
3. The `CheckOutcome` used in the mock matches the one referenced by the pool entry (`c.outcome_tier == outcome`)

- [ ] **Step 3: Commit**

```bash
git add src/integration_tests/pipeline/test_social_pipeline.py
git commit -m "test: add SocialActionConsequenceTests — conditions applied to target"
```

---

## Task 10: Full regression and roadmap update

- [ ] **Step 1: Run full integration test file**

```bash
arx test integration_tests.pipeline.test_social_pipeline
```
Expected: All tests pass. Count should be 8 (CheckContent) + 5 (ConditionContent) + 6 (SocialContent) + 4 (CharacterContent) + 4 (Availability) + 4 (Consent) + 8 (Consequence) = ~35 tests. Exact count varies if any were grouped differently.

- [ ] **Step 2: Run all affected app test suites**

```bash
arx test world.checks world.mechanics world.scenes actions --keepdb
```
Expected: All existing tests still pass. The EffectTarget.TARGET addition is backwards-compatible — existing effects using `target="self"` are unaffected.

- [ ] **Step 3: Run linting**

```bash
ruff check src/integration_tests/ src/world/checks/constants.py src/world/checks/types.py \
           src/world/mechanics/effect_handlers.py src/world/scenes/action_services.py
ruff format src/integration_tests/ src/world/checks/constants.py src/world/checks/types.py \
            src/world/mechanics/effect_handlers.py src/world/scenes/action_services.py
```

Fix any issues, re-run tests to confirm still passing.

- [ ] **Step 4: Update roadmap**

In `docs/roadmap/capabilities-and-challenges.md`, update Phase 7 to note what was built:

Under `### Phase 7: Seed Data & Content Authoring`, add a "What was built" block:

```markdown
**Pass 1 complete:**
- `src/integration_tests/game_content/` package established as the central location for
  realistic game content used in integration tests
- `CheckContent` — thin wrapper around existing social check type factories
- `ConditionContent` — 6 social conditions (Shaken, Charmed, Deceived, Smitten, Captivated, Enthralled)
- `SocialContent` — 6 consequence pools wired onto social ActionTemplates
- `CharacterContent.create_base_social_character()` — realistic character with social traits + Persona
- `integration_tests/pipeline/test_social_pipeline.py` — ~35 tests covering availability,
  consent flow, and consequence application for all 6 social actions
- `EffectTarget.TARGET` added — conditions now apply to the social action's target,
  not the initiator
```

- [ ] **Step 5: Final commit**

```bash
git add docs/roadmap/capabilities-and-challenges.md
git commit -m "docs: update roadmap with Phase 7 Pass 1 completion"
```

---

## Notes for Implementor

**Test isolation:** `setUpTestData` wraps all data creation in a transaction rolled back after the class's tests run. Individual test methods get savepoints (rolled back after each test). So `ConditionInstance` records created in one test don't leak into the next.

**Mock pattern:** `perform_check` is mocked at `actions.services.perform_check` (the import location used by `start_action_resolution`), not at `world.checks.services.perform_check`. Follow the existing pattern in `test_pipeline_integration.py`.

**CheckOutcome retrieval:** `SocialContent.create_all()` creates outcomes with canonical names ("Success", "Failure", etc.). Tests retrieve them with `CheckOutcome.objects.get(name="Success")` after calling `create_all()`. The mock's `return_value.outcome` must be this exact instance for `select_consequence_from_result`'s `c.outcome_tier == outcome` filter to match.

**If CharacterTraitValueFactory has no character field:** The factory may require `character` to be passed explicitly. If you hit a `NOT NULL` error, add `character=character` kwarg to `CharacterTraitValueFactory(...)`.

**Type annotations:** All new functions in typed apps need annotations. Check `pyproject.toml` `[tool.ty.src].include` to see if `integration_tests` is listed. If not, annotations are optional but still preferred for clarity.
