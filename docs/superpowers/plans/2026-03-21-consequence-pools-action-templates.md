# Consequence Pools & Action Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement reusable consequence pools with inheritance and data-driven action templates that unify how checks and consequences resolve across challenges, techniques, and environmental contexts.

**Architecture:** New models (ConsequencePool, ActionTemplate, ActionTemplateGate) live in the `actions` app as resolution specifications. ContextConsequencePool lives in `mechanics` for environmental consequence attachment. A state-machine pipeline (`resolve_action_template`) handles multi-step resolution with pause points. Existing challenge resolution delegates to this pipeline when an ActionTemplate is present.

**Tech Stack:** Django/Evennia (SharedMemoryModel), FactoryBoy for test data, Evennia test runner (`arx test`), ruff for linting.

**Spec:** `docs/superpowers/specs/2026-03-21-consequence-pools-and-action-templates-design.md`

**Key codebase conventions:**
- All concrete models use `SharedMemoryModel` (import from `evennia.utils.idmapper.models`)
- Absolute imports only (no relative imports)
- Type annotations required on all functions in typed apps
- TextChoices/constants go in `constants.py`, types/dataclasses go in `types.py`
- Tests use FactoryBoy with `setUpTestData` — see `django_notes.md`
- Run `ruff check <file>` and `ruff format <file>` on every changed file
- Run `arx test <app>` after changes to verify
- Line length limit: 100 characters
- `select_weighted()` reads `.weight` attribute via `getattr(item, "weight", 1)` — any object passed to it must have a `.weight` attribute
- `filter_character_loss()` reads `.character_loss` and `.weight` attributes
- Actions app uses `actions/models/` package (not single `models.py`). New models go in new modules within this package and are exported from `__init__.py`
- Avoid multiple migrations during development of a new feature — squash before merging

---

## File Map

### New Files (actions app)

| File | Responsibility |
|------|---------------|
| `src/actions/models/consequence_pools.py` | ConsequencePool and ConsequencePoolEntry models |
| `src/actions/models/action_templates.py` | ActionTemplate and ActionTemplateGate models |
| `src/actions/services.py` | `get_effective_consequences()`, `resolve_action_template()`, `start_action_resolution()`, `advance_resolution()` |
| `src/actions/types.py` (modify) | Add `WeightedConsequence`, `PendingActionResolution`, `StepResult`, `ResolutionPhase` |
| `src/actions/constants.py` (modify) | Add `Pipeline`, `GateRole`, `ActionTargetType`, `ResolutionPhase` |
| `src/actions/models/__init__.py` (modify) | Export new models |
| `src/actions/factories.py` | Factories for ConsequencePool, ConsequencePoolEntry, ActionTemplate, ActionTemplateGate |
| `src/actions/admin.py` | Admin registrations with inlines |
| `src/actions/tests/test_consequence_pools.py` | Pool model and inheritance tests |
| `src/actions/tests/test_action_templates.py` | ActionTemplate model and validation tests |
| `src/actions/tests/test_resolution_pipeline.py` | State machine and resolution flow tests |

### New Files (mechanics app)

| File | Responsibility |
|------|---------------|
| `src/world/mechanics/models.py` (modify) | Add ContextConsequencePool model |
| `src/world/mechanics/factories.py` (modify) | Add ContextConsequencePool factory |
| `src/world/mechanics/admin.py` (modify) | Add ContextConsequencePool admin |
| `src/world/mechanics/tests/test_context_pools.py` | Context pool tests |

### Modified Files (checks app)

| File | Responsibility |
|------|---------------|
| `src/world/checks/consequence_resolution.py` (modify) | Add `select_consequence_from_result()` |
| `src/world/checks/tests/test_consequence_resolution.py` (modify) | Tests for new function |

### Modified Files (existing model FKs)

| File | Responsibility |
|------|---------------|
| `src/world/mechanics/models.py` (modify) | Add `action_template` FK to ChallengeApproach |
| `src/world/magic/models.py` (modify) | Add `action_template` FK to Technique |
| `src/world/mechanics/challenge_resolution.py` (modify) | Delegate to `resolve_action_template()` when ActionTemplate present |

---

## Task 1: Constants and Types

**Files:**
- Modify: `src/actions/constants.py`
- Modify: `src/actions/types.py`

- [ ] **Step 1: Add new constants**

Add to `src/actions/constants.py`:

```python
from enum import StrEnum

from django.db import models


class Pipeline(models.TextChoices):
    """Resolution pattern for ActionTemplate."""

    SINGLE = "single", "Single Check"
    GATED = "gated", "Gated (with prerequisite checks)"


class GateRole(models.TextChoices):
    """Semantic role of an ActionTemplateGate."""

    ACTIVATION = "activation", "Activation"


class ActionTargetType(models.TextChoices):
    """Target type for data-driven ActionTemplates (mirrors TargetType StrEnum)."""

    SELF = "self", "Self"
    SINGLE = "single", "Single Target"
    AREA = "area", "Area"
    FILTERED_GROUP = "filtered_group", "Filtered Group"


class ResolutionPhase(StrEnum):
    """Phase of the action resolution state machine.

    StrEnum (not TextChoices) because this is in-memory state machine state,
    never stored in a database column.
    """

    GATE_PENDING = "gate_pending"
    GATE_RESOLVED = "gate_resolved"
    MAIN_PENDING = "main_pending"
    MAIN_RESOLVED = "main_resolved"
    CONTEXT_PENDING = "context_pending"
    COMPLETE = "complete"
```

- [ ] **Step 2: Add new types**

Add to `src/actions/types.py`:

```python
@dataclass
class WeightedConsequence:
    """A Consequence with its effective weight for a specific pool.

    Uses 'weight' attribute name so select_weighted() and filter_character_loss()
    can read it via getattr(item, "weight").
    """

    consequence: Consequence
    weight: int
    character_loss: bool  # forwarded from consequence for filter_character_loss()

    @property
    def outcome_tier(self) -> CheckOutcome:
        return self.consequence.outcome_tier

    @property
    def label(self) -> str:
        return self.consequence.label

    @property
    def pk(self) -> int | None:
        return self.consequence.pk


@dataclass
class StepResult:
    """Outcome of a single resolution step."""

    step_label: str
    check_result: CheckResult
    consequence_id: int | None  # PK of selected Consequence (None for no-op)
    applied_effect_ids: list[int] | None = None  # PKs of created instances, None until applied
    was_rerolled: bool = False


@dataclass
class PendingActionResolution:
    """State of an in-progress action template resolution."""

    template_id: int
    character_id: int
    target_difficulty: int
    resolution_context_data: dict[str, int | None]

    current_phase: str  # ResolutionPhase value
    gate_results: list[StepResult] = field(default_factory=list)
    main_result: StepResult | None = None
    context_results: list[StepResult] = field(default_factory=list)

    awaiting_confirmation: bool = False
    awaiting_intervention: bool = False
    intervention_options: list[str] = field(default_factory=list)
```

Add the necessary imports at the top of `types.py` (inside `TYPE_CHECKING` block):

```python
from world.checks.types import CheckResult
from world.traits.models import CheckOutcome
```

- [ ] **Step 3: Run linting**

Run: `ruff check src/actions/constants.py src/actions/types.py`
Run: `ruff format src/actions/constants.py src/actions/types.py`

- [ ] **Step 4: Commit**

```bash
git add src/actions/constants.py src/actions/types.py
git commit -m "feat(actions): add constants and types for consequence pools and action templates"
```

---

## Task 2: ConsequencePool and ConsequencePoolEntry Models

**Files:**
- Create: `src/actions/models/consequence_pools.py`
- Modify: `src/actions/models/__init__.py`
- Create: `src/actions/factories.py`
- Create: `src/actions/tests/test_consequence_pools.py`

- [ ] **Step 1: Write model tests**

Create `src/actions/tests/test_consequence_pools.py`:

```python
"""Tests for ConsequencePool and ConsequencePoolEntry models."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.factories import ConsequenceFactory


class ConsequencePoolModelTests(TestCase):
    """Test ConsequencePool model validation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.parent_pool = ConsequencePoolFactory(name="Parent Pool")
        cls.child_pool = ConsequencePoolFactory(
            name="Child Pool", parent=cls.parent_pool
        )

    def test_pool_creation(self) -> None:
        pool = ConsequencePoolFactory(name="Test Pool")
        assert pool.name == "Test Pool"
        assert pool.parent is None

    def test_child_pool_with_parent(self) -> None:
        assert self.child_pool.parent == self.parent_pool

    def test_grandchild_rejected(self) -> None:
        grandchild = ConsequencePoolFactory.build(
            name="Grandchild", parent=self.child_pool
        )
        with self.assertRaises(ValidationError):
            grandchild.full_clean()

    def test_self_parent_rejected(self) -> None:
        pool = ConsequencePoolFactory()
        pool.parent = pool
        with self.assertRaises(ValidationError):
            pool.full_clean()

    def test_str(self) -> None:
        assert str(self.parent_pool) == "Parent Pool"


class ConsequencePoolEntryModelTests(TestCase):
    """Test ConsequencePoolEntry model validation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.parent_pool = ConsequencePoolFactory(name="Parent")
        cls.child_pool = ConsequencePoolFactory(
            name="Child", parent=cls.parent_pool
        )
        cls.consequence = ConsequenceFactory()

    def test_entry_creation(self) -> None:
        entry = ConsequencePoolEntryFactory(
            pool=self.parent_pool, consequence=self.consequence
        )
        assert entry.pool == self.parent_pool
        assert entry.weight_override is None
        assert entry.is_excluded is False

    def test_weight_override(self) -> None:
        entry = ConsequencePoolEntryFactory(
            pool=self.parent_pool,
            consequence=self.consequence,
            weight_override=10,
        )
        assert entry.weight_override == 10

    def test_exclusion_on_parent_rejected(self) -> None:
        entry = ConsequencePoolEntryFactory.build(
            pool=self.parent_pool,
            consequence=self.consequence,
            is_excluded=True,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_exclusion_on_child_allowed(self) -> None:
        entry = ConsequencePoolEntryFactory(
            pool=self.child_pool,
            consequence=self.consequence,
            is_excluded=True,
        )
        assert entry.is_excluded is True

    def test_unique_constraint(self) -> None:
        ConsequencePoolEntryFactory(
            pool=self.parent_pool, consequence=self.consequence
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ConsequencePoolEntryFactory(
                pool=self.parent_pool, consequence=self.consequence
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test actions`
Expected: ImportError — factories and models don't exist yet.

- [ ] **Step 3: Create the models**

Create `src/actions/models/consequence_pools.py`:

```python
"""ConsequencePool and ConsequencePoolEntry models."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class ConsequencePool(SharedMemoryModel):
    """Named, reusable collection of consequences with single-depth inheritance."""

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable pool name (e.g., 'Wild Magic Surge').",
    )
    description = models.TextField(
        blank=True,
        help_text="GM authoring context for this pool.",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text="Inherit consequences from this pool (single depth only).",
    )

    class Meta:
        verbose_name = "Consequence Pool"
        verbose_name_plural = "Consequence Pools"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.parent_id == self.pk and self.pk is not None:
            raise ValidationError({"parent": "A pool cannot be its own parent."})
        if self.parent is not None and self.parent.parent_id is not None:
            raise ValidationError(
                {"parent": "Single-depth inheritance only — parent already has a parent."}
            )


class ConsequencePoolEntry(SharedMemoryModel):
    """Links a Consequence to a Pool with optional weight override or exclusion."""

    pool = models.ForeignKey(
        ConsequencePool,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    consequence = models.ForeignKey(
        "checks.Consequence",
        on_delete=models.CASCADE,
        related_name="pool_entries",
    )
    weight_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Overrides Consequence.weight for this pool. Null uses default.",
    )
    is_excluded = models.BooleanField(
        default=False,
        help_text="If True, suppresses this consequence when inherited from parent.",
    )

    class Meta:
        verbose_name = "Consequence Pool Entry"
        verbose_name_plural = "Consequence Pool Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["pool", "consequence"],
                name="unique_pool_consequence",
            ),
        ]

    def __str__(self) -> str:
        action = "excludes" if self.is_excluded else "includes"
        return f"{self.pool.name} {action} {self.consequence.label}"

    def clean(self) -> None:
        super().clean()
        if self.is_excluded and self.pool_id and not self._pool_has_parent():
            raise ValidationError(
                {"is_excluded": "Exclusion only applies to child pools with a parent."}
            )

    def _pool_has_parent(self) -> bool:
        pool = self.pool
        return pool.parent_id is not None
```

- [ ] **Step 4: Create factories**

Create `src/actions/factories.py`:

```python
"""FactoryBoy factories for actions app models."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from actions.models import ConsequencePool, ConsequencePoolEntry


class ConsequencePoolFactory(DjangoModelFactory):
    """Factory for ConsequencePool."""

    class Meta:
        model = ConsequencePool

    name = factory.Sequence(lambda n: f"Pool{n}")
    description = ""
    parent = None


class ConsequencePoolEntryFactory(DjangoModelFactory):
    """Factory for ConsequencePoolEntry."""

    class Meta:
        model = ConsequencePoolEntry

    pool = factory.SubFactory(ConsequencePoolFactory)
    consequence = factory.SubFactory("world.checks.factories.ConsequenceFactory")
    weight_override = None
    is_excluded = False
```

- [ ] **Step 5: Update models __init__.py**

Add to `src/actions/models/__init__.py`:

```python
from actions.models.consequence_pools import ConsequencePool, ConsequencePoolEntry
```

- [ ] **Step 6: Generate migration**

Run: `arx manage makemigrations actions`
Verify: migration file created with ConsequencePool and ConsequencePoolEntry tables.

- [ ] **Step 7: Apply migration and run tests**

Run: `arx manage migrate`
Run: `arx test actions`
Expected: All tests pass, including new pool tests.

- [ ] **Step 8: Lint**

Run: `ruff check src/actions/models/consequence_pools.py src/actions/factories.py src/actions/tests/test_consequence_pools.py`
Run: `ruff format src/actions/models/consequence_pools.py src/actions/factories.py src/actions/tests/test_consequence_pools.py`

- [ ] **Step 9: Commit**

```bash
git add src/actions/models/ src/actions/factories.py src/actions/tests/test_consequence_pools.py src/actions/migrations/
git commit -m "feat(actions): add ConsequencePool and ConsequencePoolEntry models"
```

---

## Task 3: get_effective_consequences() Service

**Files:**
- Create: `src/actions/services.py`
- Modify: `src/actions/tests/test_consequence_pools.py`

- [ ] **Step 1: Write tests for pool inheritance resolution**

Add to `src/actions/tests/test_consequence_pools.py`:

```python
from actions.services import get_effective_consequences


class GetEffectiveConsequencesTests(TestCase):
    """Test pool inheritance resolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome_tier = CheckOutcomeFactory()  # from world.traits.factories
        cls.parent_pool = ConsequencePoolFactory(name="Parent")
        cls.c1 = ConsequenceFactory(
            outcome_tier=cls.outcome_tier, label="C1", weight=10
        )
        cls.c2 = ConsequenceFactory(
            outcome_tier=cls.outcome_tier, label="C2", weight=20
        )
        cls.c3 = ConsequenceFactory(
            outcome_tier=cls.outcome_tier, label="C3", weight=30
        )
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.c1)
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.c2)

    def test_simple_pool_no_parent(self) -> None:
        result = get_effective_consequences(self.parent_pool)
        assert len(result) == 2
        labels = {wc.label for wc in result}
        assert labels == {"C1", "C2"}

    def test_default_weight_from_consequence(self) -> None:
        result = get_effective_consequences(self.parent_pool)
        c1_entry = next(wc for wc in result if wc.label == "C1")
        assert c1_entry.weight == 10

    def test_weight_override_on_entry(self) -> None:
        pool = ConsequencePoolFactory(name="Override Pool")
        ConsequencePoolEntryFactory(
            pool=pool, consequence=self.c1, weight_override=99
        )
        result = get_effective_consequences(pool)
        assert result[0].weight == 99

    def test_child_inherits_parent(self) -> None:
        child = ConsequencePoolFactory(name="Child", parent=self.parent_pool)
        result = get_effective_consequences(child)
        assert len(result) == 2
        labels = {wc.label for wc in result}
        assert labels == {"C1", "C2"}

    def test_child_adds_consequence(self) -> None:
        child = ConsequencePoolFactory(name="Child Add", parent=self.parent_pool)
        ConsequencePoolEntryFactory(pool=child, consequence=self.c3)
        result = get_effective_consequences(child)
        assert len(result) == 3
        labels = {wc.label for wc in result}
        assert labels == {"C1", "C2", "C3"}

    def test_child_excludes_parent_consequence(self) -> None:
        child = ConsequencePoolFactory(name="Child Excl", parent=self.parent_pool)
        ConsequencePoolEntryFactory(
            pool=child, consequence=self.c1, is_excluded=True
        )
        result = get_effective_consequences(child)
        assert len(result) == 1
        assert result[0].label == "C2"

    def test_child_overrides_parent_weight(self) -> None:
        child = ConsequencePoolFactory(
            name="Child Weight", parent=self.parent_pool
        )
        ConsequencePoolEntryFactory(
            pool=child, consequence=self.c1, weight_override=50
        )
        result = get_effective_consequences(child)
        c1_entry = next(wc for wc in result if wc.label == "C1")
        assert c1_entry.weight == 50

    def test_empty_pool_returns_empty_list(self) -> None:
        pool = ConsequencePoolFactory(name="Empty")
        result = get_effective_consequences(pool)
        assert result == []

    def test_child_excludes_all_returns_empty(self) -> None:
        child = ConsequencePoolFactory(
            name="Child Empty", parent=self.parent_pool
        )
        ConsequencePoolEntryFactory(
            pool=child, consequence=self.c1, is_excluded=True
        )
        ConsequencePoolEntryFactory(
            pool=child, consequence=self.c2, is_excluded=True
        )
        result = get_effective_consequences(child)
        assert result == []

    def test_character_loss_forwarded(self) -> None:
        loss_c = ConsequenceFactory(
            outcome_tier=self.outcome_tier,
            label="Death",
            weight=1,
            character_loss=True,
        )
        pool = ConsequencePoolFactory(name="Loss Pool")
        ConsequencePoolEntryFactory(pool=pool, consequence=loss_c)
        result = get_effective_consequences(pool)
        assert result[0].character_loss is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test actions.tests.test_consequence_pools.GetEffectiveConsequencesTests`
Expected: ImportError — `get_effective_consequences` not defined.

- [ ] **Step 3: Implement the service**

Create `src/actions/services.py`:

```python
"""Service functions for action resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.types import WeightedConsequence

if TYPE_CHECKING:
    from actions.models import ConsequencePool
    from actions.models.consequence_pools import ConsequencePoolEntry


def get_effective_consequences(pool: ConsequencePool) -> list[WeightedConsequence]:
    """Resolve pool inheritance into a flat list of weighted consequences.

    For pools without a parent, returns the pool's own entries.
    For child pools, starts with the parent's entries, then applies
    the child's modifications (additions, exclusions, weight overrides).
    """
    entries = list(pool.entries.select_related("consequence"))

    if pool.parent_id is None:
        return _entries_to_weighted(entries)

    # Start with parent's effective consequences
    parent_entries = list(pool.parent.entries.select_related("consequence"))
    parent_by_consequence_id: dict[int, WeightedConsequence] = {}
    for entry in parent_entries:
        if entry.is_excluded:
            continue
        wc = _entry_to_weighted(entry)
        parent_by_consequence_id[entry.consequence_id] = wc

    # Apply child modifications
    for entry in entries:
        cid = entry.consequence_id
        if entry.is_excluded:
            parent_by_consequence_id.pop(cid, None)
        elif cid in parent_by_consequence_id:
            # Override weight
            if entry.weight_override is not None:
                parent_by_consequence_id[cid] = _entry_to_weighted(entry)
        else:
            # Add new consequence
            parent_by_consequence_id[cid] = _entry_to_weighted(entry)

    return list(parent_by_consequence_id.values())


def _entries_to_weighted(
    entries: list[ConsequencePoolEntry],
) -> list[WeightedConsequence]:
    """Convert pool entries to WeightedConsequence list, skipping excluded."""
    return [_entry_to_weighted(e) for e in entries if not e.is_excluded]


def _entry_to_weighted(entry: ConsequencePoolEntry) -> WeightedConsequence:
    """Convert a single ConsequencePoolEntry to WeightedConsequence."""
    consequence = entry.consequence
    weight_override = entry.weight_override
    return WeightedConsequence(
        consequence=consequence,
        weight=weight_override if weight_override is not None else consequence.weight,
        character_loss=consequence.character_loss,
    )
```

- [ ] **Step 4: Run tests**

Run: `arx test actions`
Expected: All tests pass.

- [ ] **Step 5: Lint and commit**

Run: `ruff check src/actions/services.py` and `ruff format src/actions/services.py`

```bash
git add src/actions/services.py src/actions/tests/test_consequence_pools.py
git commit -m "feat(actions): add get_effective_consequences() pool inheritance resolution"
```

---

## Task 4: ActionTemplate and ActionTemplateGate Models

**Files:**
- Create: `src/actions/models/action_templates.py`
- Modify: `src/actions/models/__init__.py`
- Modify: `src/actions/factories.py`
- Create: `src/actions/tests/test_action_templates.py`

- [ ] **Step 1: Write model tests**

Create `src/actions/tests/test_action_templates.py`:

```python
"""Tests for ActionTemplate and ActionTemplateGate models."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import GateRole, Pipeline
from actions.factories import (
    ActionTemplateFactory,
    ActionTemplateGateFactory,
    ConsequencePoolFactory,
)


class ActionTemplateModelTests(TestCase):
    """Test ActionTemplate model validation."""

    def test_creation(self) -> None:
        template = ActionTemplateFactory(name="Fire Bolt")
        assert template.name == "Fire Bolt"
        assert template.pipeline == Pipeline.SINGLE

    def test_str(self) -> None:
        template = ActionTemplateFactory(name="Fire Bolt")
        assert str(template) == "Fire Bolt"

    def test_single_pipeline_with_gate_rejected(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.SINGLE)
        ActionTemplateGateFactory(action_template=template)
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_gated_pipeline_without_gate_rejected(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.GATED)
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_gated_pipeline_with_gate_valid(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.GATED)
        ActionTemplateGateFactory(action_template=template)
        template.full_clean()  # Should not raise


class ActionTemplateGateModelTests(TestCase):
    """Test ActionTemplateGate model validation."""

    def test_creation(self) -> None:
        gate = ActionTemplateGateFactory()
        assert gate.gate_role == GateRole.ACTIVATION
        assert gate.failure_aborts is True

    def test_gate_without_consequence_pool(self) -> None:
        gate = ActionTemplateGateFactory(consequence_pool=None)
        assert gate.consequence_pool is None

    def test_str(self) -> None:
        template = ActionTemplateFactory(name="Fire Bolt")
        gate = ActionTemplateGateFactory(
            action_template=template, gate_role=GateRole.ACTIVATION
        )
        assert "Fire Bolt" in str(gate)
        assert "ACTIVATION" in str(gate).upper() or "Activation" in str(gate)

    def test_unique_constraint_role_per_template(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.GATED)
        ActionTemplateGateFactory(
            action_template=template, gate_role=GateRole.ACTIVATION
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ActionTemplateGateFactory(
                action_template=template, gate_role=GateRole.ACTIVATION
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test actions`
Expected: ImportError — models and factories don't exist yet.

- [ ] **Step 3: Create the models**

Create `src/actions/models/action_templates.py`:

```python
"""ActionTemplate and ActionTemplateGate models."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import ActionTargetType, GateRole, Pipeline
from actions.models.consequence_pools import ConsequencePool


class ActionTemplate(SharedMemoryModel):
    """Data-driven resolution specification for authored actions.

    Defines what happens when a character performs a data-driven action:
    which check type to use, which consequence pool to resolve, and
    what pipeline pattern to follow.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable name (e.g., 'Fire Bolt', 'Pick Lock').",
    )
    description = models.TextField(
        blank=True,
        help_text="Narrative description of this action.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="action_templates",
        help_text="Check type for the main resolution step.",
    )
    consequence_pool = models.ForeignKey(
        ConsequencePool,
        on_delete=models.PROTECT,
        related_name="action_templates",
        help_text="Consequence pool for the main resolution step.",
    )
    pipeline = models.CharField(
        max_length=20,
        choices=Pipeline.choices,
        default=Pipeline.SINGLE,
        help_text="Resolution pattern: SINGLE (one check) or GATED (prerequisite checks first).",
    )
    target_type = models.CharField(
        max_length=20,
        choices=ActionTargetType.choices,
        default=ActionTargetType.SELF,
        help_text="What kind of target this action operates on.",
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Frontend icon identifier.",
    )
    category = models.CharField(
        max_length=50,
        help_text="Grouping category (e.g., 'magic', 'combat', 'exploration').",
    )

    class Meta:
        verbose_name = "Action Template"
        verbose_name_plural = "Action Templates"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.pk is None:
            return  # Can't validate gate count before first save
        gate_count = self.gates.count()
        if self.pipeline == Pipeline.SINGLE and gate_count > 0:
            raise ValidationError(
                {"pipeline": "SINGLE pipeline cannot have gates."}
            )
        if self.pipeline == Pipeline.GATED and gate_count == 0:
            raise ValidationError(
                {"pipeline": "GATED pipeline requires at least one gate."}
            )


class ActionTemplateGate(SharedMemoryModel):
    """Optional extra check step that gates an ActionTemplate's main resolution."""

    action_template = models.ForeignKey(
        ActionTemplate,
        on_delete=models.CASCADE,
        related_name="gates",
    )
    gate_role = models.CharField(
        max_length=20,
        choices=GateRole.choices,
        default=GateRole.ACTIVATION,
        help_text="Semantic role of this gate.",
    )
    step_order = models.IntegerField(
        default=0,
        help_text="Execution order (lower = earlier). Negative = before main step.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="action_template_gates",
        help_text="Check type for this gate.",
    )
    consequence_pool = models.ForeignKey(
        ConsequencePool,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_template_gates",
        help_text="Gate-specific consequences. Null = pure go/no-go check.",
    )
    failure_aborts = models.BooleanField(
        default=True,
        help_text="If True, failing this gate stops the pipeline.",
    )

    class Meta:
        verbose_name = "Action Template Gate"
        verbose_name_plural = "Action Template Gates"
        ordering = ["step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["action_template", "gate_role"],
                name="unique_template_gate_role",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action_template.name} - {self.get_gate_role_display()}"
```

- [ ] **Step 4: Add factories**

Add to `src/actions/factories.py`:

```python
from actions.models import ActionTemplate, ActionTemplateGate
from actions.constants import ActionTargetType, GateRole, Pipeline


class ActionTemplateFactory(DjangoModelFactory):
    """Factory for ActionTemplate."""

    class Meta:
        model = ActionTemplate

    name = factory.Sequence(lambda n: f"Template{n}")
    description = ""
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    consequence_pool = factory.SubFactory(ConsequencePoolFactory)
    pipeline = Pipeline.SINGLE
    target_type = ActionTargetType.SELF
    icon = ""
    category = "test"


class ActionTemplateGateFactory(DjangoModelFactory):
    """Factory for ActionTemplateGate."""

    class Meta:
        model = ActionTemplateGate

    action_template = factory.SubFactory(
        ActionTemplateFactory, pipeline=Pipeline.GATED
    )
    gate_role = GateRole.ACTIVATION
    step_order = 0
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    consequence_pool = factory.SubFactory(ConsequencePoolFactory)
    failure_aborts = True
```

- [ ] **Step 5: Update models __init__.py**

Add to `src/actions/models/__init__.py`:

```python
from actions.models.action_templates import ActionTemplate, ActionTemplateGate
```

- [ ] **Step 6: Generate and apply migration**

Run: `arx manage makemigrations actions`
Run: `arx manage migrate`

- [ ] **Step 7: Run tests**

Run: `arx test actions`
Expected: All tests pass.

- [ ] **Step 8: Lint and commit**

Run: `ruff check` and `ruff format` on all changed files.

```bash
git add src/actions/models/ src/actions/factories.py src/actions/tests/test_action_templates.py src/actions/migrations/
git commit -m "feat(actions): add ActionTemplate and ActionTemplateGate models"
```

---

## Task 5: select_consequence_from_result()

**Files:**
- Modify: `src/world/checks/consequence_resolution.py`
- Modify or create: `src/world/checks/tests/test_consequence_resolution.py`

- [ ] **Step 1: Write tests**

Find the existing test file for consequence resolution and add:

```python
from django.test import TestCase

from actions.types import WeightedConsequence
from evennia_extensions.factories import ObjectDBFactory
from world.checks.consequence_resolution import select_consequence_from_result
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.traits.factories import CheckOutcomeFactory


class SelectConsequenceFromResultTests(TestCase):
    """Test consequence selection using an existing check result."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Set up check infrastructure (CheckType, Traits, etc.)
        # Use existing factories from checks app
        cls.check_type = CheckTypeFactory()
        cls.outcome_success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.outcome_failure = CheckOutcomeFactory(name="Failure", success_level=0)
        cls.consequence_a = ConsequenceFactory(
            outcome_tier=cls.outcome_success, label="Good A", weight=10
        )
        cls.consequence_b = ConsequenceFactory(
            outcome_tier=cls.outcome_success, label="Good B", weight=90
        )
        cls.consequence_fail = ConsequenceFactory(
            outcome_tier=cls.outcome_failure, label="Bad", weight=1
        )

    def test_selects_from_matching_tier(self) -> None:
        check_result = CheckResult(
            check_type=self.check_type,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        weighted = [
            WeightedConsequence(
                consequence=self.consequence_a, weight=10, character_loss=False
            ),
            WeightedConsequence(
                consequence=self.consequence_b, weight=90, character_loss=False
            ),
            WeightedConsequence(
                consequence=self.consequence_fail, weight=1, character_loss=False
            ),
        ]
        character = ObjectDBFactory(db_key="Tester")
        result = select_consequence_from_result(character, check_result, weighted)
        assert result.check_result == check_result
        # Selected consequence should be from success tier
        assert result.selected_consequence.outcome_tier == self.outcome_success

    def test_empty_list_returns_fallback(self) -> None:
        check_result = CheckResult(
            check_type=self.check_type,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        character = ObjectDBFactory(db_key="Tester")
        result = select_consequence_from_result(character, check_result, [])
        assert result.selected_consequence.pk is None  # Synthetic fallback
```

- [ ] **Step 2: Implement the function**

Add to `src/world/checks/consequence_resolution.py`:

```python
def select_consequence_from_result(
    character: "ObjectDB",
    check_result: CheckResult,
    consequences: list[WeightedConsequence],
) -> PendingResolution:
    """Select a consequence using an existing check result.

    Same tier filtering, weighted selection, and character loss filtering
    as select_consequence(), but skips perform_check() — reuses the
    provided result. Used for context pools that share the main action's roll.

    WeightedConsequence exposes .weight, .character_loss, .outcome_tier
    attributes so select_weighted() and filter_character_loss() work via
    duck-typed getattr().
    """
    from world.checks.models import Consequence as ConsequenceModel  # noqa: PLC0415

    outcome = check_result.outcome
    tier_consequences = [c for c in consequences if c.outcome_tier == outcome]

    if tier_consequences:
        selected = select_weighted(tier_consequences)
        selected = filter_character_loss(character, selected, tier_consequences)
    else:
        selected = ConsequenceModel(
            outcome_tier=outcome,
            label=str(outcome.name) if outcome else "Unknown",
            weight=1,
            character_loss=False,
        )

    return PendingResolution(
        check_result=check_result,
        selected_consequence=selected,
    )
```

Add to the imports at the top of `consequence_resolution.py`:

```python
if TYPE_CHECKING:
    from actions.types import WeightedConsequence
```

(The existing `TYPE_CHECKING` block exists — add `WeightedConsequence` to it.)

- [ ] **Step 3: Run tests**

Run: `arx test checks`
Expected: All tests pass.

- [ ] **Step 4: Lint and commit**

```bash
git add src/world/checks/consequence_resolution.py src/world/checks/tests/
git commit -m "feat(checks): add select_consequence_from_result() for shared check results"
```

---

## Task 6: ContextConsequencePool Model (Mechanics App)

**Files:**
- Modify: `src/world/mechanics/models.py`
- Modify: `src/world/mechanics/factories.py`
- Modify: `src/world/mechanics/admin.py`
- Create: `src/world/mechanics/tests/test_context_pools.py`

- [ ] **Step 1: Write tests**

Create `src/world/mechanics/tests/test_context_pools.py`:

```python
"""Tests for ContextConsequencePool model."""

from django.test import TestCase

from world.mechanics.factories import ContextConsequencePoolFactory


class ContextConsequencePoolModelTests(TestCase):
    """Test ContextConsequencePool model."""

    def test_creation_rider_mode(self) -> None:
        ctx_pool = ContextConsequencePoolFactory(check_type=None)
        assert ctx_pool.check_type is None  # Rider mode

    def test_creation_reactive_mode(self) -> None:
        ctx_pool = ContextConsequencePoolFactory()
        assert ctx_pool.check_type is not None  # Reactive mode

    def test_str(self) -> None:
        ctx_pool = ContextConsequencePoolFactory()
        assert ctx_pool.property.name in str(ctx_pool)

    def test_unique_constraint(self) -> None:
        ctx_pool = ContextConsequencePoolFactory()
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ContextConsequencePoolFactory(
                property=ctx_pool.property,
                consequence_pool=ctx_pool.consequence_pool,
            )
```

- [ ] **Step 2: Add the model**

Add to `src/world/mechanics/models.py` (at the end of the file, after existing models):

```python
class ContextConsequencePool(SharedMemoryModel):
    """Links a ConsequencePool to a Property for environmental consequences.

    Rider mode (check_type=null): fires alongside player-initiated actions,
    sharing the action's check result.
    Reactive mode (check_type set): fires without player action using its
    own check type (traps, hazards, environmental effects).
    """

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="context_consequence_pools",
    )
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.PROTECT,
        related_name="context_attachments",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="context_consequence_pools",
        help_text="If set, pool can fire reactively without player action.",
    )
    description = models.TextField(
        blank=True,
        help_text="GM-facing note about this context pool.",
    )

    class Meta:
        verbose_name = "Context Consequence Pool"
        verbose_name_plural = "Context Consequence Pools"
        constraints = [
            models.UniqueConstraint(
                fields=["property", "consequence_pool"],
                name="unique_property_consequence_pool",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.property.name} → {self.consequence_pool.name}"
```

- [ ] **Step 3: Add factory**

Add to `src/world/mechanics/factories.py`:

```python
from actions.factories import ConsequencePoolFactory


class ContextConsequencePoolFactory(DjangoModelFactory):
    """Factory for ContextConsequencePool."""

    class Meta:
        model = ContextConsequencePool

    property = factory.SubFactory(PropertyFactory)
    consequence_pool = factory.SubFactory(ConsequencePoolFactory)
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    description = ""
```

- [ ] **Step 4: Add admin registration**

Add to `src/world/mechanics/admin.py`:

```python
@admin.register(ContextConsequencePool)
class ContextConsequencePoolAdmin(admin.ModelAdmin):
    list_display = ("property", "consequence_pool", "check_type")
    list_filter = ("property",)
    raw_id_fields = ("consequence_pool",)
```

- [ ] **Step 5: Generate migration, apply, and test**

Run: `arx manage makemigrations mechanics`
Run: `arx manage migrate`
Run: `arx test mechanics`
Expected: All tests pass.

- [ ] **Step 6: Lint and commit**

```bash
git add src/world/mechanics/models.py src/world/mechanics/factories.py src/world/mechanics/admin.py src/world/mechanics/tests/test_context_pools.py src/world/mechanics/migrations/
git commit -m "feat(mechanics): add ContextConsequencePool model"
```

---

## Task 7: FK Additions to ChallengeApproach and Technique

**Files:**
- Modify: `src/world/mechanics/models.py` (ChallengeApproach)
- Modify: `src/world/magic/models.py` (Technique)

- [ ] **Step 1: Add action_template FK to ChallengeApproach**

Add to ChallengeApproach in `src/world/mechanics/models.py`:

```python
action_template = models.ForeignKey(
    "actions.ActionTemplate",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="challenge_approaches",
    help_text="When set, resolution uses this template's check_type and pool.",
)
```

- [ ] **Step 2: Add action_template FK to Technique**

Add to Technique in `src/world/magic/models.py`:

```python
action_template = models.ForeignKey(
    "actions.ActionTemplate",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="techniques",
    help_text="Resolution spec for using this technique outside challenge contexts.",
)
```

- [ ] **Step 3: Generate and apply migrations**

Run: `arx manage makemigrations mechanics magic`
Run: `arx manage migrate`

- [ ] **Step 4: Run existing tests to ensure no breakage**

Run: `arx test mechanics`
Run: `arx test magic`
Expected: All existing tests pass — FK is nullable so no data migration needed.

- [ ] **Step 5: Commit**

```bash
git add src/world/mechanics/models.py src/world/magic/models.py src/world/mechanics/migrations/ src/world/magic/migrations/
git commit -m "feat: add nullable action_template FK to ChallengeApproach and Technique"
```

---

## Task 8: Admin Registrations for Actions App

**Files:**
- Create: `src/actions/admin.py`

- [ ] **Step 1: Create admin with inlines**

Create `src/actions/admin.py`:

```python
"""Django admin registrations for actions app models."""

from django.contrib import admin

from actions.models import (
    ActionTemplate,
    ActionTemplateGate,
    ConsequencePool,
    ConsequencePoolEntry,
)


class ConsequencePoolEntryInline(admin.TabularInline):
    model = ConsequencePoolEntry
    extra = 1
    raw_id_fields = ("consequence",)


@admin.register(ConsequencePool)
class ConsequencePoolAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    list_filter = ("parent",)
    search_fields = ("name",)
    inlines = [ConsequencePoolEntryInline]


class ActionTemplateGateInline(admin.TabularInline):
    model = ActionTemplateGate
    extra = 0
    raw_id_fields = ("consequence_pool",)


@admin.register(ActionTemplate)
class ActionTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "pipeline", "check_type", "consequence_pool", "category")
    list_filter = ("pipeline", "category")
    search_fields = ("name",)
    raw_id_fields = ("consequence_pool",)
    inlines = [ActionTemplateGateInline]
```

- [ ] **Step 2: Verify admin loads**

Run: `arx test actions` (ensures admin imports don't break).

- [ ] **Step 3: Commit**

```bash
git add src/actions/admin.py
git commit -m "feat(actions): add Django admin for ConsequencePool and ActionTemplate"
```

---

## Task 9: Resolution Pipeline State Machine

**Files:**
- Modify: `src/actions/services.py`
- Create: `src/actions/tests/test_resolution_pipeline.py`

This is the largest task. The state machine implements `start_action_resolution()` and
`advance_resolution()`.

- [ ] **Step 1: Write tests for SINGLE pipeline (no gates)**

Create `src/actions/tests/test_resolution_pipeline.py`:

```python
"""Tests for the action resolution pipeline state machine."""

from unittest.mock import patch

from django.test import TestCase

from actions.constants import Pipeline, ResolutionPhase
from actions.factories import (
    ActionTemplateFactory,
    ActionTemplateGateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from actions.services import advance_resolution, start_action_resolution
from evennia_extensions.factories import ObjectDBFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.types import CheckResult, ResolutionContext
from world.traits.factories import CheckOutcomeFactory


class SinglePipelineTests(TestCase):
    """Test SINGLE pipeline resolution (one check, one pool)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome = CheckOutcomeFactory(name="Success", success_level=1)
        cls.check_type = CheckTypeFactory()
        cls.pool = ConsequencePoolFactory(name="Test Pool")
        cls.consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Good Result", weight=1
        )
        ConsequencePoolEntryFactory(pool=cls.pool, consequence=cls.consequence)
        cls.template = ActionTemplateFactory(
            name="Simple Action",
            pipeline=Pipeline.SINGLE,
            check_type=cls.check_type,
            consequence_pool=cls.pool,
        )

    @patch("actions.services.perform_check")
    @patch("actions.services.apply_resolution")
    def test_single_pipeline_resolves_to_complete(
        self, mock_apply, mock_check
    ) -> None:
        mock_check.return_value = CheckResult(
            check_type=self.check_type,
            outcome=self.outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        mock_apply.return_value = []

        character = ObjectDBFactory(db_key="Alice")
        context = ResolutionContext(character=character)

        pending = start_action_resolution(
            character=character,
            template=self.template,
            target_difficulty=10,
            context=context,
        )
        # SINGLE pipeline with no dangerous consequences should resolve immediately
        assert pending.current_phase == ResolutionPhase.COMPLETE
        assert pending.main_result is not None
        assert len(pending.gate_results) == 0
```

- [ ] **Step 2: Write tests for GATED pipeline**

Add to the same file:

```python
class GatedPipelineTests(TestCase):
    """Test GATED pipeline resolution with activation gate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome_success = CheckOutcomeFactory(
            name="Success", success_level=1
        )
        cls.outcome_failure = CheckOutcomeFactory(
            name="Failure", success_level=0
        )
        cls.check_type = CheckTypeFactory()
        cls.gate_check_type = CheckTypeFactory()

        cls.main_pool = ConsequencePoolFactory(name="Main Pool")
        cls.main_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_success, label="Main Result"
        )
        ConsequencePoolEntryFactory(
            pool=cls.main_pool, consequence=cls.main_consequence
        )

        cls.gate_pool = ConsequencePoolFactory(name="Gate Pool")
        cls.gate_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_failure, label="Backlash"
        )
        ConsequencePoolEntryFactory(
            pool=cls.gate_pool, consequence=cls.gate_consequence
        )

        cls.template = ActionTemplateFactory(
            name="Gated Action",
            pipeline=Pipeline.GATED,
            check_type=cls.check_type,
            consequence_pool=cls.main_pool,
        )
        ActionTemplateGateFactory(
            action_template=cls.template,
            check_type=cls.gate_check_type,
            consequence_pool=cls.gate_pool,
            failure_aborts=True,
        )

    @patch("actions.services.apply_resolution")
    @patch("actions.services.perform_check")
    def test_gate_passes_then_main_resolves(
        self, mock_check, mock_apply
    ) -> None:
        # Gate succeeds, main succeeds
        mock_check.return_value = CheckResult(
            check_type=self.check_type,
            outcome=self.outcome_success,
            chart=None, roller_rank=None, target_rank=None,
            rank_difference=0, trait_points=0, aspect_bonus=0, total_points=0,
        )
        mock_apply.return_value = []

        character = ObjectDBFactory(db_key="Bob")
        context = ResolutionContext(character=character)

        pending = start_action_resolution(
            character=character,
            template=self.template,
            target_difficulty=10,
            context=context,
        )
        assert pending.current_phase == ResolutionPhase.COMPLETE
        assert len(pending.gate_results) == 1
        assert pending.main_result is not None

    @patch("actions.services.apply_resolution")
    @patch("actions.services.perform_check")
    def test_gate_fails_aborts_pipeline(
        self, mock_check, mock_apply
    ) -> None:
        # Gate fails
        mock_check.return_value = CheckResult(
            check_type=self.gate_check_type,
            outcome=self.outcome_failure,
            chart=None, roller_rank=None, target_rank=None,
            rank_difference=0, trait_points=0, aspect_bonus=0, total_points=0,
        )
        mock_apply.return_value = []

        character = ObjectDBFactory(db_key="Carol")
        context = ResolutionContext(character=character)

        pending = start_action_resolution(
            character=character,
            template=self.template,
            target_difficulty=10,
            context=context,
        )
        # Gate failed with failure_aborts=True — pipeline stops
        assert pending.current_phase == ResolutionPhase.GATE_RESOLVED
        assert len(pending.gate_results) == 1
        assert pending.main_result is None
```

- [ ] **Step 3: Write tests for confirmation pause points**

Add tests for character loss in gate pool triggering `awaiting_confirmation`.

- [ ] **Step 4: Implement the state machine**

Add to `src/actions/services.py`:

The implementation should include:
- `start_action_resolution(character, template, target_difficulty, context)` → `PendingActionResolution`
- `advance_resolution(pending, context, player_decision)` → `PendingActionResolution`
- Internal helpers: `_run_gate()`, `_run_main_step()`, `_run_context_pools()`
- Character loss detection for pause point: check if any consequence in the pool has `character_loss=True`
- Reroll support: if `decision="reroll"`, re-run `select_consequence_from_result()` on the current step

Key implementation details:
- Call `get_effective_consequences(pool)` for each pool
- Call `perform_check()` for gates and main step (new check each time)
- Call `select_consequence_from_result()` for context pools (reuse main step's check result)
- Call `apply_resolution()` for each step that has a selected consequence
- Build `ResolutionContext` from `resolution_context_data` PKs when resuming

- [ ] **Step 5: Run tests**

Run: `arx test actions`
Expected: All tests pass.

- [ ] **Step 6: Lint and commit**

```bash
git add src/actions/services.py src/actions/tests/test_resolution_pipeline.py
git commit -m "feat(actions): implement resolution pipeline state machine"
```

---

## Task 10: Integration — resolve_challenge() Delegation

**Files:**
- Modify: `src/world/mechanics/challenge_resolution.py`
- Modify: `src/world/mechanics/tests/test_challenge_resolution.py`

- [ ] **Step 1: Write integration test**

Add to existing challenge resolution tests:

```python
def test_resolve_challenge_delegates_to_action_template(self) -> None:
    """When approach has action_template, resolution uses the template pipeline."""
    template = ActionTemplateFactory(
        check_type=self.approach.check_type,
        consequence_pool=self.pool,
    )
    self.approach.action_template = template
    self.approach.save()

    result = resolve_challenge(
        self.character, self.challenge_instance, self.approach, self.capability_source
    )
    assert result.consequence is not None
    # Verify challenge bookkeeping still happens
    assert CharacterChallengeRecord.objects.filter(
        character=self.character,
        challenge_instance=self.challenge_instance,
    ).exists()
```

- [ ] **Step 2: Update resolve_challenge()**

Modify `src/world/mechanics/challenge_resolution.py` to check if `approach.action_template`
exists. If so, use `start_action_resolution()` instead of the inline check+select flow.
The challenge bookkeeping (deactivation, record creation) still happens in
`resolve_challenge()` after the template resolves.

Key: this is a gradual migration. If `approach.action_template is None`, the existing
code path runs unchanged.

- [ ] **Step 3: Run full test suites**

Run: `arx test mechanics`
Run: `arx test actions`
Run: `arx test checks`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/world/mechanics/challenge_resolution.py src/world/mechanics/tests/
git commit -m "feat(mechanics): resolve_challenge delegates to ActionTemplate when present"
```

---

## Task 11: Squash Migrations and Final Verification

**Files:**
- `src/actions/migrations/`
- `src/world/mechanics/migrations/`
- `src/world/magic/migrations/`

- [ ] **Step 1: Squash actions migrations**

Since this is development, squash all new actions migrations into one:

Run: `arx manage squashmigrations actions <first_new> <last_new>`

Or delete all new migration files and re-run `arx manage makemigrations actions`.

- [ ] **Step 2: Run full test suite**

Run: `arx test actions`
Run: `arx test mechanics`
Run: `arx test magic`
Run: `arx test checks`
Expected: All pass.

- [ ] **Step 3: Final lint check**

Run: `ruff check src/actions/ src/world/checks/consequence_resolution.py src/world/mechanics/models.py src/world/magic/models.py`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: squash migrations for consequence pools feature"
```

---

## Summary

| Task | What | Tests |
|------|------|-------|
| 1 | Constants and types | — |
| 2 | ConsequencePool + ConsequencePoolEntry models | Model validation |
| 3 | get_effective_consequences() | Inheritance resolution |
| 4 | ActionTemplate + ActionTemplateGate models | Model validation |
| 5 | select_consequence_from_result() | Tier selection with shared result |
| 6 | ContextConsequencePool model | Model + constraints |
| 7 | FK additions (ChallengeApproach, Technique) | Existing tests pass |
| 8 | Admin registrations | Import verification |
| 9 | Resolution pipeline state machine | SINGLE, GATED, pause points |
| 10 | resolve_challenge() delegation | Integration test |
| 11 | Squash migrations | Full suite verification |
