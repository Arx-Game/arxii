# Post-Effect System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the JSONField-based effect vocabulary with FK-backed config models and implement the generic `apply_condition_on_check` handler.

**Architecture:** Each effect type is a concrete Django model inheriting from an abstract `BaseEffectConfig`, with proper FKs to the entities it references. `effects.py` becomes an `effects/` package. Handlers are plain functions dispatched by config model type via a registry dict. `ActionEnhancement.apply()` queries all config tables and dispatches to handlers.

**Tech Stack:** Django models (SharedMemoryModel for configs), existing `perform_check()` and `apply_condition()` service functions, FactoryBoy for test data.

**Design doc:** `docs/plans/2026-03-02-post-effect-system-design.md`

**Test command:** `arx test actions`
**Lint command:** `ruff check src/actions/`
**Broader regression:** `arx test actions commands flows typeclasses`

---

### Task 1: Scaffold the effects package

Replace `effects.py` with an `effects/` package. No behavior changes yet — just restructure.

**Files:**
- Delete: `src/actions/effects.py`
- Create: `src/actions/effects/__init__.py`
- Create: `src/actions/effects/registry.py`
- Create: `src/actions/effects/base.py`
- Create: `src/actions/effects/kwargs.py`
- Create: `src/actions/effects/modifiers.py`
- Create: `src/actions/effects/conditions.py`

**Step 1: Delete old effects.py and create package**

Delete `src/actions/effects.py`. Create the package directory with empty modules:

```python
# src/actions/effects/__init__.py
"""Effect system — dispatches enhancement configs to typed handler functions."""

from actions.effects.registry import apply_effects

__all__ = ["apply_effects"]
```

```python
# src/actions/effects/registry.py
"""Handler registry and dispatch for effect configs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models import ActionEnhancement
    from actions.types import ActionContext


def apply_effects(enhancement: ActionEnhancement, context: ActionContext) -> None:
    """Query all effect configs for this enhancement and dispatch to handlers.

    Placeholder — will be implemented in Task 6.
    """
```

```python
# src/actions/effects/base.py
"""Shared reusable steps for effect handlers."""

from __future__ import annotations
```

```python
# src/actions/effects/kwargs.py
"""Handler for ModifyKwargsConfig effects."""

from __future__ import annotations
```

```python
# src/actions/effects/modifiers.py
"""Handler for AddModifierConfig effects."""

from __future__ import annotations
```

```python
# src/actions/effects/conditions.py
"""Handler for ConditionOnCheckConfig effects."""

from __future__ import annotations
```

**Step 2: Update ActionEnhancement.apply() import**

In `src/actions/models.py`, change the import in `apply()`:

```python
# Before:
from actions.effects import apply_standard_effects
apply_standard_effects(context, self.effect_parameters)

# After:
from actions.effects import apply_effects
apply_effects(self, context)
```

**Step 3: Verify existing tests still pass**

Run: `arx test actions`

Expected: All 34 tests pass. The `apply_effects` placeholder is called but does nothing,
so tests that depend on effects (Loud, Alluring Voice, involuntary integration) will fail.
That's expected — we'll fix them in later tasks.

Actually — the mock-based tests that set `mock_enh.apply = lambda ctx: ...` bypass
`apply_effects` entirely, so those should still pass. Only the DB-backed scenario tests
will fail. Verify which tests fail and confirm the failures are expected.

**Step 4: Lint**

Run: `ruff check src/actions/`

**Step 5: Commit**

```
refactor: convert effects.py to effects/ package

Scaffolds the effects package structure. apply_effects is a placeholder
that will be implemented once config models exist.
```

---

### Task 2: Create effect config models

Add `BaseEffectConfig` abstract model and three concrete config models. Remove
`effect_parameters` JSONField from `ActionEnhancement`.

**Files:**
- Create: `src/actions/effect_configs.py` (models for effect configs)
- Modify: `src/actions/models.py` (remove `effect_parameters` field)
- Modify: `src/actions/constants.py` (add `TransformType` choices)

**Step 1: Add TransformType choices to constants.py**

```python
# Add to src/actions/constants.py

class TransformType(models.TextChoices):
    """Named transforms for kwarg modification."""

    UPPERCASE = "uppercase", "Uppercase"
    LOWERCASE = "lowercase", "Lowercase"
```

**Step 2: Create effect config models**

```python
# src/actions/effect_configs.py
"""Effect config models — FK-backed parameter records for enhancement effects.

Each effect type is a concrete model inheriting from BaseEffectConfig.
An ActionEnhancement can have multiple config rows across different tables,
ordered by execution_order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import TransformType

if TYPE_CHECKING:
    pass


class BaseEffectConfig(models.Model):
    """Abstract base for all effect config models.

    Provides the FK back to ActionEnhancement and execution ordering.
    Concrete subclasses add typed fields and FKs specific to their effect type.
    """

    enhancement = models.ForeignKey(
        "actions.ActionEnhancement",
        on_delete=models.CASCADE,
        related_name="%(class)s_configs",
    )
    execution_order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["execution_order"]


class ModifyKwargsConfig(BaseEffectConfig, SharedMemoryModel):
    """Apply a named transform to an action kwarg value.

    Example: transform="uppercase" on kwarg_name="text" uppercases the speech text.
    """

    kwarg_name = models.CharField(max_length=50)
    transform = models.CharField(max_length=20, choices=TransformType.choices)

    class Meta(BaseEffectConfig.Meta):
        pass

    def __str__(self) -> str:
        return f"{self.transform} on {self.kwarg_name}"


class AddModifierConfig(BaseEffectConfig, SharedMemoryModel):
    """Add a key-value modifier to context.modifiers.

    Actions read specific modifier keys during execute(). For example,
    a combat action reads modifiers["check_bonus"].
    """

    modifier_key = models.CharField(max_length=50)
    modifier_value = models.IntegerField()

    class Meta(BaseEffectConfig.Meta):
        pass

    def __str__(self) -> str:
        return f"{self.modifier_key}={self.modifier_value}"


class ConditionOnCheckConfig(BaseEffectConfig, SharedMemoryModel):
    """Apply a condition to the target, gated by a check roll.

    The generic "attempt to put an effect on someone" pattern:
    1. Check immunity (skip if target has immunity_condition)
    2. Roll attacker's check_type vs defender's resistance
    3. On success: apply condition with severity and duration
    4. On failure: optionally apply immunity_condition

    Difficulty resolution:
    - If resistance_check_type is set and the target has traits, compute
      difficulty from the target's weighted trait points.
    - If target_difficulty is set, use it as a fixed fallback (NPCs, missions).
    - If both are set, resistance_check_type takes precedence for real characters.
    """

    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Attacker's check type (weighted trait combination).",
    )
    resistance_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Defender's resistance check type. Null = use target_difficulty.",
    )
    target_difficulty = models.IntegerField(
        null=True,
        blank=True,
        help_text="Fixed difficulty fallback for NPCs/missions.",
    )
    condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Condition to apply on successful check.",
    )
    severity = models.PositiveIntegerField(default=1)
    duration_rounds = models.PositiveIntegerField(null=True, blank=True)
    immunity_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Condition to apply on failed check (short-term immunity).",
    )
    immunity_duration = models.PositiveIntegerField(null=True, blank=True)
    source_description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Narrative label for the condition source (e.g. 'Alluring Whisper').",
    )

    class Meta(BaseEffectConfig.Meta):
        pass

    def __str__(self) -> str:
        return f"{self.condition} via {self.check_type}"
```

**Step 3: Remove effect_parameters from ActionEnhancement**

In `src/actions/models.py`, remove the `effect_parameters` field and its comment:

```python
# Remove these lines:
    # JSONField justified: effect vocabularies vary by enhancement type and no
    # shared schema can cover all combinations. Each enhancement's apply()
    # method interprets its own parameters.
    effect_parameters = models.JSONField(default=dict)
```

Also update the `apply()` method docstring to remove references to `effect_parameters`
and the standard effect vocabulary.

**Step 4: Delete old migration and regenerate**

```bash
rm src/actions/migrations/0001_initial.py
arx manage makemigrations actions
```

**Step 5: Apply migration**

```bash
arx manage migrate
```

**Step 6: Lint**

Run: `ruff check src/actions/`

**Step 7: Commit**

```
feat: add effect config models, remove effect_parameters JSONField

BaseEffectConfig abstract model with concrete ModifyKwargsConfig,
AddModifierConfig, and ConditionOnCheckConfig. Each has proper FKs
to the entities it references. Replaces the untyped JSONField.
```

---

### Task 3: Write and implement the ModifyKwargsConfig handler (TDD)

**Files:**
- Test: `src/actions/tests/test_effects.py`
- Implement: `src/actions/effects/kwargs.py`
- Implement: `src/actions/effects/registry.py`

**Step 1: Write the failing test**

```python
# src/actions/tests/test_effects.py
"""Tests for the effects system — handlers and dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from actions.effect_configs import ModifyKwargsConfig
from actions.effects.kwargs import handle_modify_kwargs
from actions.types import ActionContext, ActionResult


class ModifyKwargsHandlerTests(TestCase):
    """Test that handle_modify_kwargs transforms kwarg values."""

    def _make_context(self, **kwargs: object) -> ActionContext:
        """Build a minimal ActionContext for testing."""
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs=dict(kwargs),
            scene_data=MagicMock(),
        )

    def test_uppercase_transform(self) -> None:
        context = self._make_context(text="hello world")
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="uppercase",
        )
        handle_modify_kwargs(context, config)
        assert context.kwargs["text"] == "HELLO WORLD"

    def test_lowercase_transform(self) -> None:
        context = self._make_context(text="HELLO WORLD")
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="lowercase",
        )
        handle_modify_kwargs(context, config)
        assert context.kwargs["text"] == "hello world"

    def test_missing_kwarg_is_ignored(self) -> None:
        context = self._make_context(other="value")
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="uppercase",
        )
        handle_modify_kwargs(context, config)
        assert "text" not in context.kwargs
        assert context.kwargs["other"] == "value"

    def test_non_string_value_is_ignored(self) -> None:
        context = self._make_context(text=42)
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="uppercase",
        )
        handle_modify_kwargs(context, config)
        assert context.kwargs["text"] == 42
```

**Step 2: Run tests to verify they fail**

Run: `arx test actions.tests.test_effects`

Expected: ImportError or similar — `handle_modify_kwargs` doesn't exist yet.

**Step 3: Implement the handler**

```python
# src/actions/effects/kwargs.py
"""Handler for ModifyKwargsConfig effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.constants import TransformType

if TYPE_CHECKING:
    from actions.effect_configs import ModifyKwargsConfig
    from actions.types import ActionContext

KWARG_TRANSFORMS: dict[str, callable] = {
    TransformType.UPPERCASE: lambda v: v.upper() if isinstance(v, str) else v,
    TransformType.LOWERCASE: lambda v: v.lower() if isinstance(v, str) else v,
}


def handle_modify_kwargs(context: ActionContext, config: ModifyKwargsConfig) -> None:
    """Apply a named transform to a kwarg value."""
    transform = KWARG_TRANSFORMS.get(config.transform)
    if transform and config.kwarg_name in context.kwargs:
        context.kwargs[config.kwarg_name] = transform(context.kwargs[config.kwarg_name])
```

**Step 4: Run tests to verify they pass**

Run: `arx test actions.tests.test_effects`

Expected: 4 tests pass.

**Step 5: Lint**

Run: `ruff check src/actions/effects/`

**Step 6: Commit**

```
feat: add ModifyKwargsConfig handler with TDD

handle_modify_kwargs applies named transforms (uppercase, lowercase)
to action kwargs. Tests cover transforms, missing kwargs, non-string values.
```

---

### Task 4: Write and implement the AddModifierConfig handler (TDD)

**Files:**
- Modify: `src/actions/tests/test_effects.py`
- Implement: `src/actions/effects/modifiers.py`

**Step 1: Write the failing test**

Append to `src/actions/tests/test_effects.py`:

```python
from actions.effect_configs import AddModifierConfig
from actions.effects.modifiers import handle_add_modifier


class AddModifierHandlerTests(TestCase):
    """Test that handle_add_modifier sets context.modifiers values."""

    def _make_context(self) -> ActionContext:
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs={},
            scene_data=MagicMock(),
        )

    def test_adds_modifier_to_context(self) -> None:
        context = self._make_context()
        config = AddModifierConfig(modifier_key="check_bonus", modifier_value=5)
        handle_add_modifier(context, config)
        assert context.modifiers["check_bonus"] == 5

    def test_overwrites_existing_modifier(self) -> None:
        context = self._make_context()
        context.modifiers["check_bonus"] = 3
        config = AddModifierConfig(modifier_key="check_bonus", modifier_value=10)
        handle_add_modifier(context, config)
        assert context.modifiers["check_bonus"] == 10
```

**Step 2: Run tests to verify they fail**

Run: `arx test actions.tests.test_effects`

Expected: ImportError — `handle_add_modifier` doesn't exist yet.

**Step 3: Implement the handler**

```python
# src/actions/effects/modifiers.py
"""Handler for AddModifierConfig effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.effect_configs import AddModifierConfig
    from actions.types import ActionContext


def handle_add_modifier(context: ActionContext, config: AddModifierConfig) -> None:
    """Set a key-value modifier in context.modifiers."""
    context.modifiers[config.modifier_key] = config.modifier_value
```

**Step 4: Run tests to verify they pass**

Run: `arx test actions.tests.test_effects`

Expected: 6 tests pass (4 kwargs + 2 modifier).

**Step 5: Commit**

```
feat: add AddModifierConfig handler with TDD
```

---

### Task 5: Write and implement ConditionOnCheckConfig handler and shared steps (TDD)

This is the largest task. The handler orchestrates shared steps that call existing
service functions.

**Files:**
- Modify: `src/actions/tests/test_effects.py`
- Implement: `src/actions/effects/base.py` (shared steps)
- Implement: `src/actions/effects/conditions.py` (handler)

**Step 1: Write the failing tests**

Append to `src/actions/tests/test_effects.py`:

```python
from unittest.mock import patch

from actions.effect_configs import ConditionOnCheckConfig
from actions.effects.conditions import handle_condition_on_check
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import ConditionTemplateFactory


class ConditionOnCheckHandlerTests(TestCase):
    """Test the generic apply-condition-on-check handler."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_category = CheckCategoryFactory(name="Social")
        cls.attack_check = CheckTypeFactory(
            name="charm_attack", category=cls.check_category,
        )
        cls.defense_check = CheckTypeFactory(
            name="charm_defense", category=cls.check_category,
        )
        cls.charmed = ConditionTemplateFactory(name="Charmed")
        cls.charm_immunity = ConditionTemplateFactory(name="Charm Immunity")

    def _make_context(self) -> ActionContext:
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=MagicMock(),
            kwargs={},
            scene_data=MagicMock(),
            result=ActionResult(success=True),
        )

    def _make_config(self, **overrides: object) -> ConditionOnCheckConfig:
        defaults = {
            "check_type": self.attack_check,
            "resistance_check_type": self.defense_check,
            "condition": self.charmed,
            "severity": 2,
            "duration_rounds": 5,
            "immunity_condition": self.charm_immunity,
            "immunity_duration": 3,
            "source_description": "Alluring Whisper",
        }
        defaults.update(overrides)
        return ConditionOnCheckConfig(**defaults)

    def _successful_check_result(self) -> CheckResult:
        """A CheckResult where success_level > 0."""
        result = MagicMock(spec=CheckResult)
        result.success_level = 1
        return result

    def _failed_check_result(self) -> CheckResult:
        """A CheckResult where success_level <= 0."""
        result = MagicMock(spec=CheckResult)
        result.success_level = -1
        return result

    @patch("actions.effects.conditions.has_condition", return_value=False)
    @patch("actions.effects.conditions.apply_condition")
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=30)
    def test_successful_check_applies_condition(
        self, mock_resolve, mock_check, mock_apply, mock_immune,
    ) -> None:
        mock_check.return_value = self._successful_check_result()
        mock_apply.return_value = MagicMock(success=True)
        context = self._make_context()
        config = self._make_config()

        handle_condition_on_check(context, config)

        mock_apply.assert_called_once_with(
            context.target,
            self.charmed,
            severity=2,
            duration_rounds=5,
            source_character=context.actor,
            source_description="Alluring Whisper",
        )

    @patch("actions.effects.conditions.has_condition", return_value=False)
    @patch("actions.effects.conditions.apply_condition")
    @patch("actions.effects.conditions.apply_immunity_on_fail")
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=30)
    def test_failed_check_applies_immunity(
        self, mock_resolve, mock_check, mock_immunity, mock_apply, mock_immune,
    ) -> None:
        mock_check.return_value = self._failed_check_result()
        context = self._make_context()
        config = self._make_config()

        handle_condition_on_check(context, config)

        mock_apply.assert_not_called()
        mock_immunity.assert_called_once_with(
            context.target, self.charm_immunity, 3,
        )

    @patch("actions.effects.conditions.has_condition", return_value=True)
    @patch("actions.effects.conditions.perform_check")
    def test_immune_target_skips_check(
        self, mock_check, mock_immune,
    ) -> None:
        context = self._make_context()
        config = self._make_config()

        handle_condition_on_check(context, config)

        mock_check.assert_not_called()

    @patch("actions.effects.conditions.has_condition", return_value=False)
    @patch("actions.effects.conditions.apply_condition")
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=30)
    def test_no_immunity_condition_skips_immunity_on_fail(
        self, mock_resolve, mock_check, mock_apply, mock_immune,
    ) -> None:
        mock_check.return_value = self._failed_check_result()
        context = self._make_context()
        config = self._make_config(immunity_condition=None)

        handle_condition_on_check(context, config)

        mock_apply.assert_not_called()

    def test_no_target_skips_entirely(self) -> None:
        context = self._make_context()
        context.target = None
        config = self._make_config()

        # Should not raise
        handle_condition_on_check(context, config)
```

**Step 2: Run tests to verify they fail**

Run: `arx test actions.tests.test_effects`

Expected: ImportError — `handle_condition_on_check` doesn't exist.

**Step 3: Implement shared steps in effects/base.py**

```python
# src/actions/effects/base.py
"""Shared reusable steps for effect handlers.

These are discrete functions that handlers compose. Each wraps an existing
service function with the parameter resolution needed by the effects system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.conditions.models import ConditionTemplate


def check_immunity(target: ObjectDB, immunity_condition: ConditionTemplate | None) -> bool:
    """Return True if the target is immune (has the immunity condition)."""
    if immunity_condition is None:
        return False
    from world.conditions.services import has_condition  # noqa: PLC0415

    return has_condition(target, immunity_condition)


def resolve_target_difficulty(
    target: ObjectDB,
    resistance_check_type: CheckType | None,
    fallback_difficulty: int | None,
) -> int:
    """Compute the target's resistance as a point total for target_difficulty.

    Uses the target's traits through the standard check pipeline if
    resistance_check_type is set. Falls back to a fixed value for
    synthetic NPCs or mission contexts.
    """
    if resistance_check_type is not None:
        from world.checks.services import calculate_trait_points_for_check_type  # noqa: PLC0415

        try:
            points = calculate_trait_points_for_check_type(target, resistance_check_type)
            if points > 0:
                return points
        except (AttributeError, TypeError):
            pass  # Target has no traits — fall through to fallback

    return fallback_difficulty or 0


def apply_immunity_on_fail(
    target: ObjectDB,
    immunity_condition: ConditionTemplate,
    immunity_duration: int | None,
) -> None:
    """Apply a short-term immunity condition after a failed check."""
    from world.conditions.services import apply_condition  # noqa: PLC0415

    apply_condition(
        target,
        immunity_condition,
        severity=1,
        duration_rounds=immunity_duration,
        source_description="Immunity from failed effect",
    )
```

**Important note:** `calculate_trait_points_for_check_type` may not exist as a public
function in `checks/services.py`. The existing `perform_check` calculates trait points
internally via `_calculate_trait_points(handler, check_type)`. The implementer should
check whether this helper needs to be extracted as a public function, or whether calling
`perform_check` with `target_difficulty=0` and reading `total_points` from the result
is a better approach for getting the defender's point total.

If `_calculate_trait_points` is private, the simplest approach is:

```python
def resolve_target_difficulty(target, resistance_check_type, fallback_difficulty):
    if resistance_check_type is not None:
        try:
            # Use perform_check with difficulty=0 to get the target's raw points
            from world.checks.services import perform_check
            result = perform_check(target, resistance_check_type, target_difficulty=0)
            if result.total_points > 0:
                return result.total_points
        except (AttributeError, TypeError):
            pass
    return fallback_difficulty or 0
```

The implementer should verify which approach works and adjust accordingly.

**Step 4: Implement the handler in effects/conditions.py**

```python
# src/actions/effects/conditions.py
"""Handler for ConditionOnCheckConfig effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.effects.base import apply_immunity_on_fail, check_immunity, resolve_target_difficulty

if TYPE_CHECKING:
    from actions.effect_configs import ConditionOnCheckConfig
    from actions.types import ActionContext


def handle_condition_on_check(context: ActionContext, config: ConditionOnCheckConfig) -> None:
    """Apply a condition to the target, gated by a check roll.

    Steps:
    1. Skip if no target
    2. Check immunity — skip if target has immunity_condition
    3. Resolve target difficulty from resistance_check_type or fixed value
    4. Roll attacker's check_type vs resolved difficulty
    5. On success: apply condition
    6. On failure: apply immunity if configured
    """
    if context.target is None:
        return

    # Step 1: Check immunity
    if check_immunity(context.target, config.immunity_condition):
        return

    # Step 2: Resolve difficulty
    target_difficulty = resolve_target_difficulty(
        context.target, config.resistance_check_type, config.target_difficulty,
    )

    # Step 3: Roll
    from world.checks.services import perform_check  # noqa: PLC0415

    result = perform_check(context.actor, config.check_type, target_difficulty=target_difficulty)

    # Step 4: Apply condition or immunity
    if result.success_level > 0:
        from world.conditions.services import apply_condition  # noqa: PLC0415

        apply_condition(
            context.target,
            config.condition,
            severity=config.severity,
            duration_rounds=config.duration_rounds,
            source_character=context.actor,
            source_description=config.source_description,
        )
    elif config.immunity_condition is not None and config.immunity_duration is not None:
        apply_immunity_on_fail(
            context.target, config.immunity_condition, config.immunity_duration,
        )
```

**Step 5: Run tests to verify they pass**

Run: `arx test actions.tests.test_effects`

Expected: All tests pass (4 kwargs + 2 modifier + 5 condition = 11).

**Step 6: Commit**

```
feat: add ConditionOnCheckConfig handler and shared steps with TDD

Generic apply-condition-on-check pattern: check immunity, resolve
difficulty from target traits or fixed value, roll check, apply
condition on success, apply immunity on failure.
```

---

### Task 6: Implement dispatch — apply_effects and get_all_configs (TDD)

Wire the registry so `apply_effects(enhancement, context)` queries all config
tables and dispatches to the correct handler.

**Files:**
- Modify: `src/actions/tests/test_effects.py`
- Implement: `src/actions/effects/registry.py`

**Step 1: Write the failing test**

Append to `src/actions/tests/test_effects.py`:

```python
from actions.constants import EnhancementSourceType
from actions.effect_configs import AddModifierConfig, ModifyKwargsConfig
from actions.effects import apply_effects
from actions.models import ActionEnhancement
from evennia_extensions.factories import ObjectDBFactory
from world.distinctions.factories import DistinctionFactory


class ApplyEffectsDispatchTests(TestCase):
    """Test that apply_effects queries configs and dispatches to handlers."""

    def test_dispatches_modify_kwargs_config(self) -> None:
        distinction = DistinctionFactory(name="Loud Dispatch", slug="loud-dispatch")
        enh = ActionEnhancement.objects.create(
            base_action_key="say",
            variant_name="Test",
            is_involuntary=False,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )
        ModifyKwargsConfig.objects.create(
            enhancement=enh, kwarg_name="text", transform="uppercase",
        )

        context = ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs={"text": "hello"},
            scene_data=MagicMock(),
        )
        apply_effects(enh, context)
        assert context.kwargs["text"] == "HELLO"

    def test_dispatches_add_modifier_config(self) -> None:
        distinction = DistinctionFactory(name="Strong Dispatch", slug="strong-dispatch")
        enh = ActionEnhancement.objects.create(
            base_action_key="attack",
            variant_name="Test",
            is_involuntary=False,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )
        AddModifierConfig.objects.create(
            enhancement=enh, modifier_key="check_bonus", modifier_value=5,
        )

        context = ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs={},
            scene_data=MagicMock(),
        )
        apply_effects(enh, context)
        assert context.modifiers["check_bonus"] == 5

    def test_multiple_configs_applied_in_execution_order(self) -> None:
        distinction = DistinctionFactory(name="Multi Dispatch", slug="multi-dispatch")
        enh = ActionEnhancement.objects.create(
            base_action_key="say",
            variant_name="Test",
            is_involuntary=False,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )
        # Uppercase first, then add modifier
        ModifyKwargsConfig.objects.create(
            enhancement=enh, kwarg_name="text", transform="uppercase",
            execution_order=0,
        )
        AddModifierConfig.objects.create(
            enhancement=enh, modifier_key="voice_effect", modifier_value=1,
            execution_order=1,
        )

        context = ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs={"text": "hello"},
            scene_data=MagicMock(),
        )
        apply_effects(enh, context)
        assert context.kwargs["text"] == "HELLO"
        assert context.modifiers["voice_effect"] == 1

    def test_no_configs_does_nothing(self) -> None:
        distinction = DistinctionFactory(name="Empty Dispatch", slug="empty-dispatch")
        enh = ActionEnhancement.objects.create(
            base_action_key="say",
            variant_name="Test",
            is_involuntary=False,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )
        context = ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs={"text": "hello"},
            scene_data=MagicMock(),
        )
        apply_effects(enh, context)
        assert context.kwargs["text"] == "hello"
```

**Step 2: Run tests to verify they fail**

Run: `arx test actions.tests.test_effects`

Expected: `apply_effects` is the placeholder that does nothing, so the first three
tests should fail on assertions.

**Step 3: Implement the registry and dispatch**

```python
# src/actions/effects/registry.py
"""Handler registry and dispatch for effect configs."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from actions.effect_configs import AddModifierConfig, ConditionOnCheckConfig, ModifyKwargsConfig
from actions.effects.conditions import handle_condition_on_check
from actions.effects.kwargs import handle_modify_kwargs
from actions.effects.modifiers import handle_add_modifier

if TYPE_CHECKING:
    from actions.effect_configs import BaseEffectConfig
    from actions.models import ActionEnhancement
    from actions.types import ActionContext

# Each entry maps a concrete config model class to its handler function.
# To add a new effect type: create the model, write the handler, add it here.
HANDLER_REGISTRY: dict[
    type[BaseEffectConfig],
    Callable[[ActionContext, BaseEffectConfig], None],
] = {
    ModifyKwargsConfig: handle_modify_kwargs,
    AddModifierConfig: handle_add_modifier,
    ConditionOnCheckConfig: handle_condition_on_check,
}


def get_all_configs(enhancement: ActionEnhancement) -> list[BaseEffectConfig]:
    """Query all config tables for configs belonging to this enhancement.

    Returns configs from all registered types, sorted by execution_order.
    """
    configs: list[BaseEffectConfig] = []
    for config_class in HANDLER_REGISTRY:
        configs.extend(
            config_class.objects.filter(enhancement=enhancement)
        )
    configs.sort(key=lambda c: c.execution_order)
    return configs


def apply_effects(enhancement: ActionEnhancement, context: ActionContext) -> None:
    """Query all effect configs for this enhancement and dispatch to handlers."""
    for config in get_all_configs(enhancement):
        handler = HANDLER_REGISTRY[type(config)]
        handler(context, config)
```

**Step 4: Run tests to verify they pass**

Run: `arx test actions.tests.test_effects`

Expected: All tests pass (4 + 2 + 5 + 4 = 15).

**Step 5: Commit**

```
feat: implement effect dispatch registry with TDD

apply_effects queries all config tables for an enhancement and
dispatches to typed handler functions in execution_order.
```

---

### Task 7: Update scenario tests for the new config models (TDD)

Update the Loud and Alluring Voice scenario tests to use config model rows
instead of JSON effect_parameters. Update the involuntary integration test too.

**Files:**
- Modify: `src/actions/tests/test_enhancements.py`

**Step 1: Update the imports**

Add:
```python
from actions.effect_configs import AddModifierConfig, ConditionOnCheckConfig, ModifyKwargsConfig
```

Remove any references to `effect_parameters` in test data.

**Step 2: Update InvoluntaryEnhancementIntegrationTests**

Change from:
```python
ActionEnhancement.objects.create(
    ...,
    effect_parameters={"add_modifiers": {"check_bonus": 10}},
)
```

To:
```python
enh = ActionEnhancement.objects.create(...)
AddModifierConfig.objects.create(
    enhancement=enh, modifier_key="check_bonus", modifier_value=10,
)
```

**Step 3: Update LoudDistinctionScenarioTests**

Change from:
```python
ActionEnhancement.objects.create(
    ...,
    effect_parameters={"modify_kwargs": {"text": "uppercase"}},
)
```

To:
```python
enh = ActionEnhancement.objects.create(...)
ModifyKwargsConfig.objects.create(
    enhancement=enh, kwarg_name="text", transform="uppercase",
)
```

**Step 4: Update AlluringVoiceTechniqueScenarioTests**

This is the big one. Change from checking `result.data["post_effects_applied"]`
to verifying the condition was actually applied via `has_condition()`.

The test now needs:
- CheckType and ConditionTemplate instances (via factories)
- A `ConditionOnCheckConfig` row with real FKs
- `perform_check` patched to return a successful result
- Assertion via `has_condition(target, charmed_condition)`

```python
def test_alluring_voice_applies_charmed_condition(self) -> None:
    room = ObjectDBFactory(
        db_key="Garden",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    actor = ObjectDBFactory(
        db_key="Siren",
        db_typeclass_path="typeclasses.characters.Character",
        location=room,
    )
    target = ObjectDBFactory(
        db_key="Mark",
        db_typeclass_path="typeclasses.characters.Character",
        location=room,
    )
    technique = TechniqueFactory(name="Alluring Voice Scenario")

    check_category = CheckCategoryFactory(name="Social Scenario")
    charm_attack = CheckTypeFactory(name="charm_attack_s", category=check_category)
    charm_defense = CheckTypeFactory(name="charm_defense_s", category=check_category)
    charmed = ConditionTemplateFactory(name="Charmed Scenario")
    charm_immunity = ConditionTemplateFactory(name="Charm Immunity Scenario")

    enh = ActionEnhancement.objects.create(
        base_action_key="whisper",
        variant_name="Alluring Whisper",
        is_involuntary=False,
        source_type=EnhancementSourceType.TECHNIQUE,
        technique=technique,
    )
    ConditionOnCheckConfig.objects.create(
        enhancement=enh,
        check_type=charm_attack,
        resistance_check_type=charm_defense,
        condition=charmed,
        severity=2,
        duration_rounds=5,
        immunity_condition=charm_immunity,
        immunity_duration=3,
        source_description="Alluring Whisper",
    )

    # Mock the check to succeed and mock target.msg for WhisperAction
    successful_result = MagicMock()
    successful_result.success_level = 1

    with (
        patch("actions.effects.conditions.perform_check", return_value=successful_result),
        patch("actions.effects.conditions.resolve_target_difficulty", return_value=30),
        patch.object(target, "msg"),
    ):
        result = WhisperAction().run(
            actor,
            enhancements=[enh],
            target=target,
            text="you look lovely tonight",
        )

    assert result.success is True
    # Verify the condition was actually applied to the target
    from world.conditions.services import has_condition
    assert has_condition(target, charmed)
```

**Step 5: Run tests**

Run: `arx test actions.tests.test_enhancements`

Expected: All tests pass.

**Step 6: Run full actions suite**

Run: `arx test actions`

Expected: All tests pass.

**Step 7: Commit**

```
test: update scenario tests to use effect config models

Loud distinction uses ModifyKwargsConfig, Alluring Voice uses
ConditionOnCheckConfig with real FKs. Assertions verify actual
game-world outcomes (conditions applied) not internal data dicts.
```

---

### Task 8: Cleanup and final verification

Remove old references, ensure everything is consistent, run full regression.

**Files:**
- Modify: `src/actions/models.py` (verify apply() docstring is current)
- Modify: `src/actions/CLAUDE.md` (update documentation)
- Delete: `docs/plans/2026-03-02-post-effect-system-design.md` (design doc)
- Delete: `docs/plans/2026-03-02-post-effect-system-implementation.md` (this plan)

**Step 1: Update CLAUDE.md**

Update the Enhancement System section to reflect:
- Effect configs replace JSONField
- effects/ package structure
- Handler registry pattern
- How to add new effect types

**Step 2: Run full regression**

Run: `arx test actions commands flows typeclasses`

Expected: All tests pass.

**Step 3: Lint everything**

Run: `ruff check src/actions/`

**Step 4: Final commit**

```
docs: update actions CLAUDE.md for effect config system

Removes plan artifacts. Updates documentation to reflect
FK-backed config models, effects package, handler registry.
```

---

## Acceptance Criteria

Each criterion maps to a verification command:

| Criterion | Verification |
|---|---|
| `effect_parameters` JSONField removed from ActionEnhancement | `grep -r "effect_parameters" src/actions/models.py` returns nothing |
| ModifyKwargsConfig handler transforms kwargs | `arx test actions.tests.test_effects::ModifyKwargsHandlerTests` |
| AddModifierConfig handler sets modifiers | `arx test actions.tests.test_effects::AddModifierHandlerTests` |
| ConditionOnCheckConfig handler applies conditions | `arx test actions.tests.test_effects::ConditionOnCheckHandlerTests` |
| apply_effects dispatches by config type | `arx test actions.tests.test_effects::ApplyEffectsDispatchTests` |
| Loud distinction scenario works with config models | `arx test actions.tests.test_enhancements::LoudDistinctionScenarioTests` |
| Alluring Voice scenario applies real condition | `arx test actions.tests.test_enhancements::AlluringVoiceTechniqueScenarioTests` |
| All actions tests pass | `arx test actions` |
| No regressions | `arx test actions commands flows typeclasses` |
| Lint clean | `ruff check src/actions/` |
| No JSONField references in actions app | `grep -r "JSONField" src/actions/` returns nothing |
| Config models have proper FKs (no string references) | Visual inspection of `effect_configs.py` |
