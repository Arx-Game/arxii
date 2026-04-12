# Scope 5: Magical Alteration Resolution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `MAGICAL_SCARS` effect handler stub with a player-authored magical scar resolution system — three new models, a progression gate, library browse + author-from-scratch flows, and full API.

**Architecture:** `MagicalAlterationTemplate` (OneToOne on `ConditionTemplate`) carries magic-specific metadata. `PendingAlteration` queues unresolved scars and gates progression spending. `MagicalAlterationEvent` is the provenance audit log. All runtime effects flow through existing condition effect tables. Handler rewrite defers scar application until player resolution.

**Tech Stack:** Django, Evennia SharedMemoryModel, FactoryBoy, Django REST Framework, arx CLI

**Spec:** `docs/superpowers/specs/2026-04-12-scope5-magical-alteration-resolution-design.md`

**Convention note:** All models use `SharedMemoryModel` from `evennia.utils.idmapper.models`. All imports are absolute. TextChoices live in `constants.py`. Dataclasses live in `types.py`. Service functions accept model instances, not slugs. Test commands use `arx test`. Single migration for all new models.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/world/magic/constants.py` | **Modify.** Add `AlterationTier`, `PendingAlterationStatus` TextChoices and tier cap constants |
| `src/world/magic/types.py` | **Create.** Dataclasses for service results: `AlterationResolutionResult`, `PendingAlterationResult` |
| `src/world/magic/models.py` | **Modify.** Add `MagicalAlterationTemplate`, `PendingAlteration`, `MagicalAlterationEvent` models |
| `src/world/magic/migrations/NNNN_magical_alterations.py` | **Create.** Single migration for all three models |
| `src/world/magic/factories.py` | **Modify.** Add `MagicalAlterationTemplateFactory`, `PendingAlterationFactory`, `MagicalAlterationEventFactory` |
| `src/world/magic/services.py` | **Modify.** Add `create_pending_alteration()`, `escalate_pending_alteration()`, `resolve_pending_alteration()`, `has_pending_alterations()`, `staff_clear_alteration()`, `validate_alteration_resolution()`, `get_library_entries()` |
| `src/world/mechanics/effect_handlers.py` | **Modify.** Rewrite `_apply_magical_scars()` handler (lines 261-279) |
| `src/world/magic/serializers.py` | **Modify.** Add `PendingAlterationSerializer`, `MagicalAlterationTemplateSerializer`, `AlterationResolutionSerializer`, `LibraryEntrySerializer` |
| `src/world/magic/views.py` | **Modify.** Add `PendingAlterationViewSet` with `resolve` and `library` actions |
| `src/world/magic/urls.py` | **Modify.** Register new viewset route |
| `src/world/magic/tests/test_alteration_models.py` | **Create.** Model unit tests |
| `src/world/magic/tests/test_alteration_services.py` | **Create.** Service function tests |
| `src/world/magic/tests/test_alteration_validation.py` | **Create.** Tier schema validation tests |
| `src/world/magic/tests/test_alteration_views.py` | **Create.** API endpoint tests |
| `src/world/magic/tests/test_alteration_gate.py` | **Create.** Progression gate integration tests |
| `src/world/magic/tests/test_alteration_handler.py` | **Create.** Handler rewrite tests |
| `src/integration_tests/pipeline/test_alteration_pipeline.py` | **Create.** End-to-end integration tests |
| `src/integration_tests/game_content/magic.py` | **Modify.** Add alteration pool content for integration tests |

---

## Task 1: Constants and Types

**Files:**
- Modify: `src/world/magic/constants.py`
- Create: `src/world/magic/types.py`

No tests for this task — these are pure data declarations consumed by later tasks.

- [ ] **Step 1: Add TextChoices and tier cap constants to `constants.py`**

```python
# Add to existing constants.py after CantripArchetype

class AlterationTier(models.IntegerChoices):
    """Severity tier for magical alterations. Higher = more dramatic."""

    COSMETIC_TOUCH = 1, "Cosmetic Touch"
    MARKED = 2, "Marked"
    TOUCHED = 3, "Touched"
    MARKED_PROFOUNDLY = 4, "Marked Profoundly"
    REMADE = 5, "Remade"


class PendingAlterationStatus(models.TextChoices):
    """Lifecycle status of a PendingAlteration."""

    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"
    STAFF_CLEARED = "staff_cleared", "Staff Cleared"


# Tier cap configuration. Keys are AlterationTier values.
# Each value is a dict with: social_cap, weakness_cap, resonance_cap,
# visibility_required (bool).
ALTERATION_TIER_CAPS: dict[int, dict[str, int | bool]] = {
    AlterationTier.COSMETIC_TOUCH: {
        "social_cap": 1,
        "weakness_cap": 1,
        "resonance_cap": 1,
        "visibility_required": False,
    },
    AlterationTier.MARKED: {
        "social_cap": 2,
        "weakness_cap": 2,
        "resonance_cap": 2,
        "visibility_required": False,
    },
    AlterationTier.TOUCHED: {
        "social_cap": 3,
        "weakness_cap": 3,
        "resonance_cap": 3,
        "visibility_required": False,
    },
    AlterationTier.MARKED_PROFOUNDLY: {
        "social_cap": 5,
        "weakness_cap": 5,
        "resonance_cap": 5,
        "visibility_required": True,
    },
    AlterationTier.REMADE: {
        "social_cap": 8,
        "weakness_cap": 8,
        "resonance_cap": 7,
        "visibility_required": True,
    },
}

# Minimum description length for player-authored alteration descriptions.
MIN_ALTERATION_DESCRIPTION_LENGTH = 40
```

- [ ] **Step 2: Create `types.py` with service result dataclasses**

```python
"""Dataclasses for magical alteration service layer results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.conditions.models import ConditionInstance
    from world.magic.models import (
        MagicalAlterationEvent,
        MagicalAlterationTemplate,
        PendingAlteration,
    )


class AlterationGateError(Exception):
    """Raised when a character tries to spend advancement points while
    having unresolved magical alterations."""

    user_message = (
        "You have an unresolved magical alteration. "
        "Visit the alteration screen to resolve it before "
        "spending advancement points."
    )


class AlterationResolutionError(Exception):
    """Raised when condition application fails during alteration resolution."""

    user_message = (
        "The magical alteration could not be applied due to a "
        "condition interaction. Please contact staff."
    )


@dataclass(frozen=True)
class PendingAlterationResult:
    """Result of creating or escalating a PendingAlteration."""

    pending: PendingAlteration
    created: bool  # True if new, False if escalated
    previous_tier: int | None  # Non-null if escalated


@dataclass(frozen=True)
class AlterationResolutionResult:
    """Result of resolving a PendingAlteration."""

    pending: PendingAlteration
    template: MagicalAlterationTemplate
    condition_instance: ConditionInstance
    event: MagicalAlterationEvent
```

- [ ] **Step 3: Commit**

```
git add src/world/magic/constants.py src/world/magic/types.py
git commit -m "feat(magic): add alteration constants, tier caps, and result types"
```

---

## Task 2: Models

**Files:**
- Modify: `src/world/magic/models.py`
- Create: `src/world/magic/migrations/NNNN_magical_alterations.py` (via makemigrations)
- Create: `src/world/magic/tests/test_alteration_models.py`

- [ ] **Step 1: Write model creation tests**

Create `src/world/magic/tests/test_alteration_models.py`:

```python
"""Tests for MagicalAlterationTemplate, PendingAlteration, MagicalAlterationEvent."""

from django.test import TestCase
from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import (
    AffinityFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import (
    MagicalAlterationEvent,
    MagicalAlterationTemplate,
    PendingAlteration,
)


class MagicalAlterationTemplateTests(BaseEvenniaTest):
    """Test MagicalAlterationTemplate model."""

    @classmethod
    def setUpTestData(cls):
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)
        cls.condition_template = ConditionTemplateFactory(
            name="Voice of Many",
        )

    def test_create_template(self):
        """MagicalAlterationTemplate can be created with all fields."""
        template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            weakness_magnitude=2,
            resonance_bonus_magnitude=3,
            social_reactivity_magnitude=1,
            is_visible_at_rest=True,
            is_library_entry=True,
        )
        assert template.tier == AlterationTier.TOUCHED
        assert template.origin_affinity == self.affinity
        assert template.condition_template == self.condition_template

    def test_str_uses_condition_name(self):
        """String representation uses the condition template name."""
        template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        assert self.condition_template.name in str(template)


class PendingAlterationTests(BaseEvenniaTest):
    """Test PendingAlteration model."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Celestial")
        cls.resonance = ResonanceFactory(
            name="Radiance", affinity=cls.affinity,
        )

    def test_create_pending(self):
        """PendingAlteration created with OPEN status by default."""
        pending = PendingAlteration.objects.create(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        assert pending.status == PendingAlterationStatus.OPEN
        assert pending.resolved_alteration is None

    def test_character_cascade_delete(self):
        """Deleting character cascades to pending alterations."""
        PendingAlteration.objects.create(
            character=self.sheet,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        char_obj = self.sheet.character
        char_obj.delete()
        assert PendingAlteration.objects.count() == 0


class MagicalAlterationEventTests(BaseEvenniaTest):
    """Test MagicalAlterationEvent model."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Primal")
        cls.resonance = ResonanceFactory(name="Storm", affinity=cls.affinity)
        cls.condition_template = ConditionTemplateFactory(
            name="Storm-Touched Skin",
        )
        cls.alteration_template = MagicalAlterationTemplate.objects.create(
            condition_template=cls.condition_template,
            tier=AlterationTier.TOUCHED,
            origin_affinity=cls.affinity,
            origin_resonance=cls.resonance,
        )

    def test_create_event(self):
        """MagicalAlterationEvent records provenance correctly."""
        event = MagicalAlterationEvent.objects.create(
            character=self.sheet,
            alteration_template=self.alteration_template,
            triggering_intensity=45,
            triggering_control=30,
            triggering_anima_deficit=15,
        )
        assert event.alteration_template == self.alteration_template
        assert event.triggering_intensity == 45
        assert event.active_condition is None  # nullable

    def test_alteration_template_protected(self):
        """Cannot delete alteration template with existing events."""
        MagicalAlterationEvent.objects.create(
            character=self.sheet,
            alteration_template=self.alteration_template,
        )
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.alteration_template.delete()
```

- [ ] **Step 2: Run tests to verify they fail**

```
arx test world.magic.tests.test_alteration_models --keepdb
```
Expected: ImportError — `MagicalAlterationTemplate` does not exist yet.

- [ ] **Step 3: Add models to `models.py`**

Add the following to the end of `src/world/magic/models.py` (after the existing models, in a new `# Magical Alterations` section):

```python
# =============================================================================
# Magical Alterations
# =============================================================================


class MagicalAlterationTemplate(SharedMemoryModel):
    """Magic-specific metadata layered on top of a ConditionTemplate.

    A magical alteration IS a condition — runtime effects (check modifiers,
    capability effects, resistance, properties, descriptions) live on the
    OneToOne'd ConditionTemplate. This table adds authoring slots, tier
    classification, and origin context.
    """

    condition_template = models.OneToOneField(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        related_name="magical_alteration",
    )
    tier = models.PositiveSmallIntegerField(
        choices=AlterationTier.choices,
        help_text="Severity tier 1 (cosmetic) through 5 (body partially remade).",
    )
    origin_affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="alteration_templates",
        help_text="Which affinity (Celestial/Primal/Abyssal) caused this.",
    )
    origin_resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="alteration_templates",
        help_text="The resonance channeled at overburn.",
    )
    weakness_damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alteration_weaknesses",
        help_text="Damage type the character is now vulnerable to.",
    )
    weakness_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text="Vulnerability magnitude, tier-bounded.",
    )
    resonance_bonus_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text="Bonus when channeling origin_resonance, tier-bounded.",
    )
    social_reactivity_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Reaction strength from magic-phobic observers. Calibrated as "
            "situational world-friction, not character-concept blocker."
        ),
    )
    is_visible_at_rest = models.BooleanField(
        default=False,
        help_text=(
            "Shows through normal clothing? Required True at tier 4+."
        ),
    )
    authored_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_alterations",
        help_text="Account that authored this. NULL = system/staff seed.",
    )
    parent_template = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="variants",
        help_text="If spun off from a library entry or prior alteration.",
    )
    is_library_entry = models.BooleanField(
        default=False,
        help_text=(
            "If True, shown to players browsing tier-matched alterations. "
            "Only staff can set this flag."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.condition_template.name} (Tier {self.tier})"


class PendingAlteration(SharedMemoryModel):
    """A magical alteration owed to a character, awaiting resolution.

    Created by the MAGICAL_SCARS effect handler. Blocks progression
    spending until resolved via library browse or author-from-scratch.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="pending_alterations",
    )
    status = models.CharField(
        max_length=20,
        choices=PendingAlterationStatus.choices,
        default=PendingAlterationStatus.OPEN,
    )
    tier = models.PositiveSmallIntegerField(
        choices=AlterationTier.choices,
        help_text="Required tier for resolved alteration. Upgradeable via same-scene escalation only.",
    )
    triggering_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_alterations",
    )
    triggering_technique = models.ForeignKey(
        Technique,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_intensity = models.IntegerField(null=True, blank=True)
    triggering_control = models.IntegerField(null=True, blank=True)
    triggering_anima_cost = models.IntegerField(null=True, blank=True)
    triggering_anima_deficit = models.IntegerField(null=True, blank=True)
    triggering_soulfray_stage = models.PositiveSmallIntegerField(
        null=True, blank=True,
    )
    audere_active = models.BooleanField(default=False)
    origin_affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="pending_alteration_origins",
    )
    origin_resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="pending_alteration_origins",
    )
    resolved_alteration = models.ForeignKey(
        MagicalAlterationTemplate,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resolved_pending",
        help_text="Set when player picks/authors a template.",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_pending_alterations",
    )
    notes = models.TextField(
        blank=True,
        help_text="Staff notes (e.g. reason for staff clear).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["character", "status"]),
        ]

    def __str__(self) -> str:
        return f"Pending Tier {self.tier} alteration for {self.character} ({self.status})"


class MagicalAlterationEvent(SharedMemoryModel):
    """Audit record: this character received this alteration at this moment.

    Created when a PendingAlteration resolves. Survives independently of
    the PendingAlteration and the ConditionInstance.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="alteration_events",
    )
    alteration_template = models.ForeignKey(
        MagicalAlterationTemplate,
        on_delete=models.PROTECT,
        related_name="application_events",
    )
    active_condition = models.ForeignKey(
        "conditions.ConditionInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alteration_events",
    )
    triggering_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_technique = models.ForeignKey(
        Technique,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_intensity = models.IntegerField(null=True, blank=True)
    triggering_control = models.IntegerField(null=True, blank=True)
    triggering_anima_cost = models.IntegerField(null=True, blank=True)
    triggering_anima_deficit = models.IntegerField(null=True, blank=True)
    triggering_soulfray_stage = models.PositiveSmallIntegerField(
        null=True, blank=True,
    )
    audere_active = models.BooleanField(default=False)
    applied_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True,
        help_text="Freeform staff/system notes.",
    )

    def __str__(self) -> str:
        return (
            f"{self.alteration_template.condition_template.name} "
            f"applied to {self.character} at {self.applied_at}"
        )
```

Remember to add the necessary imports at the top of `models.py`:
```python
from world.magic.constants import AlterationTier, PendingAlterationStatus
```

- [ ] **Step 4: Generate migration**

```
arx manage makemigrations magic
```
Expected: single migration file created with all three models.

- [ ] **Step 5: Apply migration**

```
arx manage migrate magic --keepdb
```

- [ ] **Step 6: Run model tests to verify they pass**

```
arx test world.magic.tests.test_alteration_models --keepdb
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```
git add src/world/magic/constants.py src/world/magic/types.py src/world/magic/models.py src/world/magic/migrations/ src/world/magic/tests/test_alteration_models.py
git commit -m "feat(magic): add MagicalAlterationTemplate, PendingAlteration, MagicalAlterationEvent models"
```

---

## Task 3: Factories

**Files:**
- Modify: `src/world/magic/factories.py`

- [ ] **Step 1: Add factories to `factories.py`**

Add after existing factories:

```python
class MagicalAlterationTemplateFactory(DjangoModelFactory):
    """Factory for MagicalAlterationTemplate."""

    class Meta:
        model = MagicalAlterationTemplate

    condition_template = factory.SubFactory(ConditionTemplateFactory)
    tier = AlterationTier.MARKED
    origin_affinity = factory.SubFactory(AffinityFactory)
    origin_resonance = factory.LazyAttribute(
        lambda o: ResonanceFactory(affinity=o.origin_affinity),
    )
    weakness_magnitude = 0
    resonance_bonus_magnitude = 0
    social_reactivity_magnitude = 0
    is_visible_at_rest = False
    is_library_entry = False


class PendingAlterationFactory(DjangoModelFactory):
    """Factory for PendingAlteration."""

    class Meta:
        model = PendingAlteration

    character = factory.SubFactory(CharacterSheetFactory)
    status = PendingAlterationStatus.OPEN
    tier = AlterationTier.MARKED
    origin_affinity = factory.SubFactory(AffinityFactory)
    origin_resonance = factory.LazyAttribute(
        lambda o: ResonanceFactory(affinity=o.origin_affinity),
    )


class MagicalAlterationEventFactory(DjangoModelFactory):
    """Factory for MagicalAlterationEvent."""

    class Meta:
        model = MagicalAlterationEvent

    character = factory.SubFactory(CharacterSheetFactory)
    alteration_template = factory.SubFactory(
        MagicalAlterationTemplateFactory,
    )
```

Add necessary imports at the top:
```python
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.models import (
    MagicalAlterationEvent,
    MagicalAlterationTemplate,
    PendingAlteration,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
```

- [ ] **Step 2: Verify factories work by updating model tests to use them**

Update `test_alteration_models.py` `setUpTestData` methods to use the new factories where appropriate. Run:

```
arx test world.magic.tests.test_alteration_models --keepdb
```
Expected: all tests pass using factories.

- [ ] **Step 3: Commit**

```
git add src/world/magic/factories.py src/world/magic/tests/test_alteration_models.py
git commit -m "feat(magic): add alteration factories"
```

---

## Task 4: Core Service Functions — Create and Escalate

**Files:**
- Modify: `src/world/magic/services.py`
- Create: `src/world/magic/tests/test_alteration_services.py`

- [ ] **Step 1: Write failing tests for `create_pending_alteration` and same-scene escalation**

Create `src/world/magic/tests/test_alteration_services.py`:

```python
"""Tests for magical alteration service functions."""

from django.test import TestCase
from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import (
    AffinityFactory,
    PendingAlterationFactory,
    ResonanceFactory,
)
from world.magic.models import PendingAlteration
from world.magic.services import create_pending_alteration
from world.scenes.factories import SceneFactory


class CreatePendingAlterationTests(BaseEvenniaTest):
    """Test create_pending_alteration service function."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(
            name="Shadow", affinity=cls.affinity,
        )

    def test_creates_new_pending(self):
        """Creates a new PendingAlteration when none exists for the scene."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        assert result.created is True
        assert result.pending.status == PendingAlterationStatus.OPEN
        assert result.pending.tier == AlterationTier.MARKED

    def test_creates_with_snapshot_fields(self):
        """Snapshot fields are stored on the pending."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
            triggering_intensity=50,
            triggering_control=30,
            triggering_anima_deficit=20,
            audere_active=True,
        )
        assert result.pending.triggering_intensity == 50
        assert result.pending.triggering_control == 30
        assert result.pending.audere_active is True

    def test_same_scene_escalation_upgrades_tier(self):
        """Second MAGICAL_SCARS hit in same scene upgrades existing pending."""
        scene = SceneFactory()
        result1 = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
        )
        assert result1.created is True

        result2 = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED_PROFOUNDLY,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
            triggering_intensity=80,
        )
        assert result2.created is False
        assert result2.previous_tier == AlterationTier.MARKED
        assert result2.pending.tier == AlterationTier.MARKED_PROFOUNDLY
        assert result2.pending.triggering_intensity == 80
        assert PendingAlteration.objects.filter(
            character=self.sheet,
        ).count() == 1

    def test_same_scene_no_downgrade(self):
        """Lower tier in same scene is a no-op."""
        scene = SceneFactory()
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
        )
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
        )
        assert result.created is False
        assert result.previous_tier is None  # no change
        assert result.pending.tier == AlterationTier.TOUCHED

    def test_different_scenes_create_separate_pendings(self):
        """Different scenes create independent pendings."""
        scene1 = SceneFactory()
        scene2 = SceneFactory()
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene1,
        )
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene2,
        )
        assert PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```
arx test world.magic.tests.test_alteration_services --keepdb
```
Expected: ImportError — `create_pending_alteration` not found.

- [ ] **Step 3: Implement `create_pending_alteration` in `services.py`**

Add to `src/world/magic/services.py`:

```python
from django.db import transaction

from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.models import PendingAlteration
from world.magic.types import PendingAlterationResult


def create_pending_alteration(
    *,
    character: "CharacterSheet",
    tier: int,
    origin_affinity: "Affinity",
    origin_resonance: "Resonance",
    scene: "Scene | None",
    triggering_technique: "Technique | None" = None,
    triggering_intensity: int | None = None,
    triggering_control: int | None = None,
    triggering_anima_cost: int | None = None,
    triggering_anima_deficit: int | None = None,
    triggering_soulfray_stage: int | None = None,
    audere_active: bool = False,
) -> PendingAlterationResult:
    """Create or escalate a PendingAlteration for a character.

    Same-scene dedup: if an OPEN pending exists for the same character +
    scene, upgrade its tier if the new tier is higher. Otherwise no-op.
    Different scenes (or scene=None) always create new pendings.
    """
    snapshot_fields = {
        "triggering_technique": triggering_technique,
        "triggering_intensity": triggering_intensity,
        "triggering_control": triggering_control,
        "triggering_anima_cost": triggering_anima_cost,
        "triggering_anima_deficit": triggering_anima_deficit,
        "triggering_soulfray_stage": triggering_soulfray_stage,
        "audere_active": audere_active,
    }

    if scene is not None:
        existing = PendingAlteration.objects.filter(
            character=character,
            triggering_scene=scene,
            status=PendingAlterationStatus.OPEN,
        ).first()

        if existing is not None:
            if tier > existing.tier:
                previous_tier = existing.tier
                existing.tier = tier
                for field_name, value in snapshot_fields.items():
                    setattr(existing, field_name, value)
                existing.save()
                return PendingAlterationResult(
                    pending=existing,
                    created=False,
                    previous_tier=previous_tier,
                )
            return PendingAlterationResult(
                pending=existing,
                created=False,
                previous_tier=None,
            )

    pending = PendingAlteration.objects.create(
        character=character,
        tier=tier,
        origin_affinity=origin_affinity,
        origin_resonance=origin_resonance,
        triggering_scene=scene,
        **snapshot_fields,
    )
    return PendingAlterationResult(
        pending=pending,
        created=True,
        previous_tier=None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
arx test world.magic.tests.test_alteration_services --keepdb
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add src/world/magic/services.py src/world/magic/tests/test_alteration_services.py
git commit -m "feat(magic): add create_pending_alteration with same-scene dedup"
```

---

## Task 5: Tier Validation

**Files:**
- Modify: `src/world/magic/services.py`
- Create: `src/world/magic/tests/test_alteration_validation.py`

- [ ] **Step 1: Write failing validation tests**

Create `src/world/magic/tests/test_alteration_validation.py`:

```python
"""Tests for alteration tier schema validation."""

from django.test import TestCase

from world.magic.constants import AlterationTier, MIN_ALTERATION_DESCRIPTION_LENGTH
from world.magic.factories import AffinityFactory, ResonanceFactory
from world.magic.services import validate_alteration_resolution


class ValidateAlterationResolutionTests(TestCase):
    """Test validate_alteration_resolution service function."""

    @classmethod
    def setUpTestData(cls):
        from world.conditions.factories import DamageTypeFactory  # noqa: PLC0415

        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(
            name="Shadow", affinity=cls.affinity,
        )
        cls.damage_type = DamageTypeFactory(name="Holy")

    def _valid_payload(self, **overrides):
        """Return a valid resolution payload dict with optional overrides."""
        base = {
            "tier": AlterationTier.MARKED,
            "origin_affinity_id": self.affinity.pk,
            "origin_resonance_id": self.resonance.pk,
            "name": "Test Alteration",
            "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "weakness_magnitude": 1,
            "weakness_damage_type_id": self.damage_type.pk,
            "resonance_bonus_magnitude": 1,
            "social_reactivity_magnitude": 1,
            "is_visible_at_rest": False,
        }
        base.update(overrides)
        return base

    def test_valid_payload_passes(self):
        """A well-formed payload at tier 2 passes validation."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(),
            is_staff=False,
        )
        assert errors == []

    def test_tier_mismatch_rejected(self):
        """Payload tier must match pending tier."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.TOUCHED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(tier=AlterationTier.MARKED),
            is_staff=False,
        )
        assert any("tier" in e.lower() for e in errors)

    def test_affinity_mismatch_rejected(self):
        """Payload affinity must match pending origin."""
        other_affinity = AffinityFactory(name="Celestial")
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                origin_affinity_id=other_affinity.pk,
            ),
            is_staff=False,
        )
        assert any("affinity" in e.lower() for e in errors)

    def test_weakness_exceeds_cap_rejected(self):
        """Weakness magnitude above tier cap is rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(weakness_magnitude=5),
            is_staff=False,
        )
        assert any("weakness" in e.lower() for e in errors)

    def test_resonance_bonus_exceeds_cap_rejected(self):
        """Resonance bonus above tier cap is rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(resonance_bonus_magnitude=5),
            is_staff=False,
        )
        assert any("resonance" in e.lower() for e in errors)

    def test_social_reactivity_exceeds_cap_rejected(self):
        """Social reactivity above tier cap is rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(social_reactivity_magnitude=5),
            is_staff=False,
        )
        assert any("social" in e.lower() for e in errors)

    def test_visibility_required_at_tier_4(self):
        """is_visible_at_rest must be True at tier 4+."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED_PROFOUNDLY,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                tier=AlterationTier.MARKED_PROFOUNDLY,
                weakness_magnitude=3,
                resonance_bonus_magnitude=3,
                social_reactivity_magnitude=3,
                is_visible_at_rest=False,
            ),
            is_staff=False,
        )
        assert any("visible" in e.lower() for e in errors)

    def test_description_too_short_rejected(self):
        """Descriptions below minimum length are rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(player_description="too short"),
            is_staff=False,
        )
        assert any("description" in e.lower() for e in errors)

    def test_weakness_without_damage_type_rejected(self):
        """weakness_magnitude > 0 requires weakness_damage_type."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                weakness_magnitude=1,
                weakness_damage_type_id=None,
            ),
            is_staff=False,
        )
        assert any("damage_type" in e.lower() for e in errors)

    def test_non_staff_library_entry_rejected(self):
        """Non-staff cannot set is_library_entry=True."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(is_library_entry=True),
            is_staff=False,
        )
        assert any("library" in e.lower() for e in errors)

    def test_staff_can_set_library_entry(self):
        """Staff can set is_library_entry=True."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(is_library_entry=True),
            is_staff=True,
        )
        assert errors == []

    def test_library_duplicate_rejected(self):
        """Cannot use a library entry the character already has active."""
        from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
        from world.conditions.models import ConditionInstance  # noqa: PLC0415
        from world.magic.factories import MagicalAlterationTemplateFactory  # noqa: PLC0415

        sheet = CharacterSheetFactory()
        library_entry = MagicalAlterationTemplateFactory(
            is_library_entry=True,
            tier=AlterationTier.MARKED,
        )
        # Simulate the condition already being active
        ConditionInstance.objects.create(
            target=sheet.character,
            condition=library_entry.condition_template,
            severity=1,
        )
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload={"library_entry_pk": library_entry.pk},
            is_staff=False,
            character_sheet=sheet,
        )
        assert any("already" in e.lower() for e in errors)

    def test_resonance_mismatch_rejected(self):
        """Payload resonance must match pending origin."""
        other_resonance = ResonanceFactory(
            name="Flame", affinity=self.affinity,
        )
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                origin_resonance_id=other_resonance.pk,
            ),
            is_staff=False,
        )
        assert any("resonance" in e.lower() for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

```
arx test world.magic.tests.test_alteration_validation --keepdb
```
Expected: ImportError — `validate_alteration_resolution` not found.

- [ ] **Step 3: Implement `validate_alteration_resolution`**

Add to `src/world/magic/services.py`:

```python
from world.magic.constants import (
    ALTERATION_TIER_CAPS,
    MIN_ALTERATION_DESCRIPTION_LENGTH,
)


def validate_alteration_resolution(
    *,
    pending_tier: int,
    pending_affinity_id: int,
    pending_resonance_id: int,
    payload: dict,
    is_staff: bool,
    character_sheet: "CharacterSheet | None" = None,
) -> list[str]:
    """Validate a resolution payload against the pending's tier and origin.

    Returns a list of error strings. Empty list = valid.
    character_sheet is required for library duplicate checks.
    """
    errors: list[str] = []
    tier = payload.get("tier")
    caps = ALTERATION_TIER_CAPS.get(pending_tier, {})

    if tier != pending_tier:
        errors.append(f"Tier mismatch: payload tier {tier} != pending tier {pending_tier}.")

    if payload.get("origin_affinity_id") != pending_affinity_id:
        errors.append("Origin affinity does not match the pending alteration.")

    if payload.get("origin_resonance_id") != pending_resonance_id:
        errors.append("Origin resonance does not match the pending alteration.")

    weakness = payload.get("weakness_magnitude", 0)
    if weakness > caps.get("weakness_cap", 0):
        errors.append(
            f"Weakness magnitude {weakness} exceeds tier {pending_tier} cap "
            f"of {caps['weakness_cap']}."
        )
    if weakness > 0 and not payload.get("weakness_damage_type_id"):
        errors.append("weakness_damage_type is required when weakness_magnitude > 0.")

    resonance = payload.get("resonance_bonus_magnitude", 0)
    if resonance > caps.get("resonance_cap", 0):
        errors.append(
            f"Resonance bonus magnitude {resonance} exceeds tier {pending_tier} cap "
            f"of {caps['resonance_cap']}."
        )

    social = payload.get("social_reactivity_magnitude", 0)
    if social > caps.get("social_cap", 0):
        errors.append(
            f"Social reactivity magnitude {social} exceeds tier {pending_tier} cap "
            f"of {caps['social_cap']}."
        )

    if caps.get("visibility_required") and not payload.get("is_visible_at_rest"):
        errors.append(
            f"is_visible_at_rest must be True at tier {pending_tier}."
        )

    for field in ("player_description", "observer_description"):
        value = payload.get(field, "")
        if len(value) < MIN_ALTERATION_DESCRIPTION_LENGTH:
            errors.append(
                f"{field} must be at least {MIN_ALTERATION_DESCRIPTION_LENGTH} characters "
                f"(got {len(value)})."
            )

    if payload.get("is_library_entry") and not is_staff:
        errors.append("Only staff can create library entries.")

    # Library use-as-is duplicate check
    library_pk = payload.get("library_entry_pk")
    if library_pk and character_sheet is not None:
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        library_entry = MagicalAlterationTemplate.objects.filter(
            pk=library_pk, is_library_entry=True,
        ).first()
        if library_entry is None:
            errors.append("Library entry not found or not a library entry.")
        elif ConditionInstance.objects.filter(
            target=character_sheet.character,
            condition=library_entry.condition_template,
        ).exists():
            errors.append("Character already has this condition active.")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

```
arx test world.magic.tests.test_alteration_validation --keepdb
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add src/world/magic/services.py src/world/magic/tests/test_alteration_validation.py
git commit -m "feat(magic): add alteration tier schema validation"
```

---

## Task 6: Resolution Service Function

**Files:**
- Modify: `src/world/magic/services.py`
- Modify: `src/world/magic/tests/test_alteration_services.py`

- [ ] **Step 1: Write failing tests for `resolve_pending_alteration`**

Add to `test_alteration_services.py`:

```python
from world.conditions.factories import (
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import (
    ConditionInstance,
    ConditionResistanceModifier,
)
from world.magic.factories import MagicalAlterationTemplateFactory
from world.magic.models import MagicalAlterationEvent, MagicalAlterationTemplate
from world.magic.services import (
    create_pending_alteration,
    has_pending_alterations,
    resolve_pending_alteration,
    staff_clear_alteration,
)


class ResolvePendingAlterationTests(BaseEvenniaTest):
    """Test resolve_pending_alteration service function."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(
            name="Shadow", affinity=cls.affinity,
        )
        cls.damage_type = DamageTypeFactory(name="Holy")

    def test_resolve_creates_condition_and_event(self):
        """Resolving a pending creates ConditionInstance and MagicalAlterationEvent."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        pending = result.pending

        resolution = resolve_pending_alteration(
            pending=pending,
            name="Voice of Many",
            player_description="Your voice carries echoes of others when you speak.",
            observer_description="Their voice resonates with an eerie chorus.",
            weakness_damage_type=self.damage_type,
            weakness_magnitude=2,
            resonance_bonus_magnitude=1,
            social_reactivity_magnitude=1,
            is_visible_at_rest=False,
            resolved_by=None,
        )

        # Pending is now resolved
        pending.refresh_from_db()
        assert pending.status == PendingAlterationStatus.RESOLVED
        assert pending.resolved_alteration is not None
        assert pending.resolved_at is not None

        # Template was created
        assert resolution.template.tier == AlterationTier.MARKED
        assert resolution.template.origin_affinity == self.affinity

        # Condition was applied
        assert resolution.condition_instance is not None
        assert ConditionInstance.objects.filter(
            target=self.sheet.character,
        ).exists()

        # Event was created
        assert resolution.event is not None
        assert resolution.event.character == self.sheet

    def test_resolve_creates_resistance_modifier(self):
        """Resolving with weakness creates ConditionResistanceModifier."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        resolution = resolve_pending_alteration(
            pending=result.pending,
            name="Holy Sensitivity",
            player_description="A" * 40,
            observer_description="B" * 40,
            weakness_damage_type=self.damage_type,
            weakness_magnitude=2,
            resonance_bonus_magnitude=0,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
            resolved_by=None,
        )
        ct = resolution.template.condition_template
        assert ConditionResistanceModifier.objects.filter(
            condition=ct,
            damage_type=self.damage_type,
        ).exists()


class HasPendingAlterationsTests(BaseEvenniaTest):
    """Test has_pending_alterations helper."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Primal")
        cls.resonance = ResonanceFactory(name="Storm", affinity=cls.affinity)

    def test_false_when_no_pendings(self):
        assert has_pending_alterations(self.sheet) is False

    def test_true_when_open_pending_exists(self):
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        assert has_pending_alterations(self.sheet) is True

    def test_false_after_resolution(self):
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        resolve_pending_alteration(
            pending=result.pending,
            name="Resolved Scar",
            player_description="A" * 40,
            observer_description="B" * 40,
            weakness_magnitude=0,
            resonance_bonus_magnitude=0,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
            resolved_by=None,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_false_after_staff_clear(self):
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        staff_clear_alteration(
            pending=result.pending,
            staff_account=None,
            notes="Test clear",
        )
        assert has_pending_alterations(self.sheet) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
arx test world.magic.tests.test_alteration_services --keepdb
```
Expected: ImportError for `resolve_pending_alteration`, `has_pending_alterations`, `staff_clear_alteration`.

- [ ] **Step 3: Implement `resolve_pending_alteration`, `has_pending_alterations`, `staff_clear_alteration`**

Add to `src/world/magic/services.py`:

```python
from django.utils import timezone

from world.conditions.models import ConditionResistanceModifier, ConditionTemplate
from world.conditions.services import apply_condition
from world.magic.models import MagicalAlterationEvent, MagicalAlterationTemplate
from world.magic.types import AlterationResolutionError, AlterationResolutionResult


@transaction.atomic
def resolve_pending_alteration(
    *,
    pending: PendingAlteration,
    name: str,
    player_description: str,
    observer_description: str,
    weakness_damage_type: "DamageType | None" = None,
    weakness_magnitude: int,
    resonance_bonus_magnitude: int,
    social_reactivity_magnitude: int,
    is_visible_at_rest: bool,
    resolved_by: "AccountDB | None",
    parent_template: MagicalAlterationTemplate | None = None,
    is_library_entry: bool = False,
    library_template: MagicalAlterationTemplate | None = None,
) -> AlterationResolutionResult:
    """Resolve a PendingAlteration by creating or selecting a template.

    If library_template is provided, use it directly (use-as-is path).
    Otherwise create a new ConditionTemplate + MagicalAlterationTemplate.
    In both cases: apply the condition, create the event, mark resolved.
    """
    if library_template is not None:
        alteration_template = library_template
        condition_template = library_template.condition_template
    else:
        # Create the underlying ConditionTemplate
        from world.conditions.constants import DurationType  # noqa: PLC0415

        condition_template = ConditionTemplate.objects.create(
            name=name,
            category=_get_or_create_alteration_category(),
            player_description=player_description,
            observer_description=observer_description,
            default_duration_type=DurationType.PERMANENT,
        )

        # Create effect rows
        if weakness_damage_type and weakness_magnitude > 0:
            ConditionResistanceModifier.objects.create(
                condition=condition_template,
                damage_type=weakness_damage_type,
                modifier_value=-weakness_magnitude,  # negative = vulnerability
            )

        # TODO: Create ConditionCheckModifier for social_reactivity when
        # observer targeting is resolved (Open Question #1 in spec)

        # TODO: Create resonance bonus modifier when the target model
        # for resonance bonuses is clarified

        # Create the MagicalAlterationTemplate
        alteration_template = MagicalAlterationTemplate.objects.create(
            condition_template=condition_template,
            tier=pending.tier,
            origin_affinity=pending.origin_affinity,
            origin_resonance=pending.origin_resonance,
            weakness_damage_type=weakness_damage_type,
            weakness_magnitude=weakness_magnitude,
            resonance_bonus_magnitude=resonance_bonus_magnitude,
            social_reactivity_magnitude=social_reactivity_magnitude,
            is_visible_at_rest=is_visible_at_rest,
            authored_by=resolved_by,
            parent_template=parent_template,
            is_library_entry=is_library_entry,
        )

    # Apply the condition to the character
    target_obj = pending.character.character  # CharacterSheet → ObjectDB
    result = apply_condition(target_obj, condition_template)

    if not result.success or result.instance is None:
        raise AlterationResolutionError(
            "Condition application was prevented (interaction or immunity)."
        )

    # Create the audit event
    event = MagicalAlterationEvent.objects.create(
        character=pending.character,
        alteration_template=alteration_template,
        active_condition=result.instance,
        triggering_scene=pending.triggering_scene,
        triggering_technique=pending.triggering_technique,
        triggering_intensity=pending.triggering_intensity,
        triggering_control=pending.triggering_control,
        triggering_anima_cost=pending.triggering_anima_cost,
        triggering_anima_deficit=pending.triggering_anima_deficit,
        triggering_soulfray_stage=pending.triggering_soulfray_stage,
        audere_active=pending.audere_active,
    )

    # Mark pending as resolved
    pending.status = PendingAlterationStatus.RESOLVED
    pending.resolved_alteration = alteration_template
    pending.resolved_at = timezone.now()
    pending.resolved_by = resolved_by
    pending.save()

    return AlterationResolutionResult(
        pending=pending,
        template=alteration_template,
        condition_instance=result.instance,
        event=event,
    )


def _get_or_create_alteration_category() -> "ConditionCategory":
    """Get or create the ConditionCategory for magical alterations."""
    from world.conditions.models import ConditionCategory  # noqa: PLC0415

    cat, _ = ConditionCategory.objects.get_or_create(
        name="Magical Alteration",
        defaults={"description": "Permanent magical changes from Soulfray overburn."},
    )
    return cat


def has_pending_alterations(character: "CharacterSheet") -> bool:
    """Check if this character has any unresolved magical alterations."""
    return PendingAlteration.objects.filter(
        character=character,
        status=PendingAlterationStatus.OPEN,
    ).exists()


def staff_clear_alteration(
    *,
    pending: PendingAlteration,
    staff_account: "AccountDB | None",
    notes: str = "",
) -> None:
    """Clear a PendingAlteration without resolving it. Staff escape hatch."""
    pending.status = PendingAlterationStatus.STAFF_CLEARED
    pending.resolved_by = staff_account
    pending.resolved_at = timezone.now()
    pending.notes = notes
    pending.save()
```

Note: `_get_or_create_alteration_category` creates a ConditionCategory for magical alterations. Check the existing ConditionCategory pattern in `world/conditions/` and follow it. The `apply_condition` function returns an `ApplyConditionResult` with an `instance` attribute — check `world/conditions/services.py:520` and `world/conditions/types.py` for the exact return type.

- [ ] **Step 4: Run tests to verify they pass**

```
arx test world.magic.tests.test_alteration_services --keepdb
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add src/world/magic/services.py src/world/magic/tests/test_alteration_services.py
git commit -m "feat(magic): add resolve_pending_alteration, has_pending_alterations, staff_clear_alteration"
```

---

## Task 7: Handler Rewrite

**Files:**
- Modify: `src/world/mechanics/effect_handlers.py` (lines 261-279)
- Create: `src/world/magic/tests/test_alteration_handler.py`

- [ ] **Step 1: Write failing tests for the rewritten handler**

Create `src/world/magic/tests/test_alteration_handler.py`:

```python
"""Tests for the rewritten _apply_magical_scars effect handler."""

from unittest.mock import MagicMock

from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.magic.constants import PendingAlterationStatus
from world.magic.factories import AffinityFactory, ResonanceFactory
from world.magic.models import PendingAlteration
from world.mechanics.effect_handlers import apply_effect


class ApplyMagicalScarsHandlerTests(BaseEvenniaTest):
    """Test _apply_magical_scars handler creates PendingAlteration."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(
            name="Shadow", affinity=cls.affinity,
        )

    def _make_effect(self, severity=1):
        """Create a mock ConsequenceEffect with MAGICAL_SCARS type."""
        effect = MagicMock()
        effect.effect_type = EffectType.MAGICAL_SCARS
        effect.condition_severity = severity
        effect.condition_template = None  # no longer used
        effect.target_type = "self"
        return effect

    def _make_context(self):
        """Create a mock ResolutionContext."""
        context = MagicMock()
        context.character = self.sheet.character  # ObjectDB
        # The handler needs to derive CharacterSheet, affinity, resonance
        # from the context. The exact mechanism depends on what's available
        # in ResolutionContext — check the spec and adapt.
        context.scene = None
        context.technique = None
        context.technique_intensity = None
        context.technique_control = None
        context.anima_deficit = None
        context.soulfray_stage = None
        context.audere_active = False
        return context

    def test_handler_creates_pending_alteration(self):
        """MAGICAL_SCARS handler creates a PendingAlteration, not a condition."""
        effect = self._make_effect(severity=2)
        context = self._make_context()

        result = apply_effect(effect, context)

        assert result.applied is True
        assert PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).exists()

    def test_handler_does_not_apply_condition(self):
        """Handler should NOT apply any condition directly."""
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        effect = self._make_effect(severity=1)
        context = self._make_context()

        initial_count = ConditionInstance.objects.count()
        apply_effect(effect, context)
        assert ConditionInstance.objects.count() == initial_count
```

**IMPORTANT — ResolutionContext adaptation required:** The mock uses fields (`scene`, `technique`, `technique_intensity`, etc.) that do NOT exist on the current `ResolutionContext` (which only has `character`, `challenge_instance`, `action_context`, `target`). The implementer MUST either:

1. **Extend `ResolutionContext`** in `src/world/checks/types.py` to include the needed fields (preferred if other handlers will also need them), OR
2. **Derive the data** from `challenge_instance` or `action_context` — e.g., the scene and technique can be looked up from the challenge instance's situation.

Check `src/world/checks/types.py` for current `ResolutionContext` fields and `src/actions/models/consequence_pools.py` for `ConsequenceEffect` fields. The handler needs to derive `CharacterSheet` from `context.character` (ObjectDB) via `context.character.sheet_data`, and determine affinity/resonance from the technique or character's dominant affinity. Update both the mock and handler code to match whichever approach is chosen.

- [ ] **Step 2: Run tests to verify they fail**

```
arx test world.magic.tests.test_alteration_handler --keepdb
```
Expected: tests fail because handler still applies condition directly.

- [ ] **Step 3: Rewrite `_apply_magical_scars` in `effect_handlers.py`**

Replace lines 261-279 of `src/world/mechanics/effect_handlers.py`:

```python
def _apply_magical_scars(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Create a PendingAlteration instead of directly applying a condition.

    The character must resolve this via the alteration resolution screen
    before they can spend advancement points. The severity maps to an
    alteration tier.
    """
    from world.magic.services import create_pending_alteration  # noqa: PLC0415

    target = _resolve_target(effect, context)
    sheet = target.sheet_data  # ObjectDB → CharacterSheet

    severity = effect.condition_severity or 1
    tier = _severity_to_tier(severity)

    # Derive origin from context. Adapt these lookups based on what
    # ResolutionContext carries — the technique's affinity/resonance,
    # or the character's dominant affinity if no technique context.
    affinity, resonance = _derive_alteration_origin(context, sheet)

    result = create_pending_alteration(
        character=sheet,
        tier=tier,
        origin_affinity=affinity,
        origin_resonance=resonance,
        scene=getattr(context, "scene", None),
        triggering_technique=getattr(context, "technique", None),
        triggering_intensity=getattr(context, "technique_intensity", None),
        triggering_control=getattr(context, "technique_control", None),
        triggering_anima_deficit=getattr(context, "anima_deficit", None),
        triggering_soulfray_stage=getattr(context, "soulfray_stage", None),
        audere_active=getattr(context, "audere_active", False),
    )

    verb = "escalated" if not result.created else "acquired"
    return AppliedEffect(
        effect_type=EffectType.MAGICAL_SCARS,
        description=(
            f"Magical alteration {verb}: tier {tier} pending for {target.db_key}"
        ),
        applied=True,
    )


def _severity_to_tier(severity: int) -> int:
    """Map consequence severity to alteration tier."""
    from world.magic.constants import AlterationTier  # noqa: PLC0415

    if severity <= 1:
        return AlterationTier.COSMETIC_TOUCH
    if severity <= 2:
        return AlterationTier.MARKED
    if severity <= 3:
        return AlterationTier.TOUCHED
    if severity <= 5:
        return AlterationTier.MARKED_PROFOUNDLY
    return AlterationTier.REMADE


def _derive_alteration_origin(
    context: "ResolutionContext",
    sheet: "CharacterSheet",
) -> tuple["Affinity", "Resonance"]:
    """Derive the alteration's origin affinity and resonance from context.

    If the context carries a technique, use its affinity/resonance.
    Otherwise fall back to the character's dominant affinity and first
    resonance. Adapt based on actual ResolutionContext fields.
    """
    # Implementation depends on ResolutionContext and technique model fields.
    # This is a placeholder that the implementer must flesh out by checking:
    # - Does ResolutionContext carry technique info? Check types.py
    # - Does Technique have affinity/resonance FKs? Check magic/models.py
    # - What's the fallback for non-technique contexts?
    raise NotImplementedError(
        "Adapt _derive_alteration_origin based on ResolutionContext fields"
    )
```

The implementer must check the actual `ResolutionContext` fields in `src/world/checks/types.py` and the `Technique` model to wire up `_derive_alteration_origin`. The tests should be adapted to match.

- [ ] **Step 4: Run tests to verify they pass**

```
arx test world.magic.tests.test_alteration_handler --keepdb
```
Expected: all tests pass once `_derive_alteration_origin` is implemented.

- [ ] **Step 5: Run existing effect handler tests to check for regressions**

```
arx test world.mechanics --keepdb
```
Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```
git add src/world/mechanics/effect_handlers.py src/world/magic/tests/test_alteration_handler.py
git commit -m "feat(magic): rewrite _apply_magical_scars to create PendingAlteration"
```

---

## Task 8: Progression Gate

**Files:**
- Create: `src/world/magic/tests/test_alteration_gate.py`
- Modify: spend endpoints (see list below)

The affected spend endpoints from the codebase exploration:
- `world/progression/services/spends.py` — `spend_xp_on_unlock()`
- `world/progression/views.py` — `ClaimKudosView.post()`
- `world/distinctions/views.py` — `DraftDistinctionViewSet.add()`

During implementation, grep for all spend-type service functions and viewset actions. The gate check is one line per endpoint.

- [ ] **Step 1: Write failing gate tests**

Create `src/world/magic/tests/test_alteration_gate.py`:

```python
"""Tests for progression gate integration."""

from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import AffinityFactory, PendingAlterationFactory, ResonanceFactory
from world.magic.services import has_pending_alterations


class ProgressionGateTests(BaseEvenniaTest):
    """Test that has_pending_alterations correctly gates progression."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)

    def test_gate_blocks_with_open_pending(self):
        """Gate returns True when OPEN pending exists."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        assert has_pending_alterations(self.sheet) is True

    def test_gate_allows_when_resolved(self):
        """Gate returns False when pending is RESOLVED."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.RESOLVED,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_gate_allows_when_staff_cleared(self):
        """Gate returns False when pending is STAFF_CLEARED."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.STAFF_CLEARED,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_gate_allows_when_no_pendings(self):
        """Gate returns False when no pendings exist."""
        assert has_pending_alterations(self.sheet) is False
```

- [ ] **Step 2: Run gate tests**

```
arx test world.magic.tests.test_alteration_gate --keepdb
```
Expected: all pass (has_pending_alterations already implemented in Task 6).

- [ ] **Step 3: Add gate check to spend endpoints**

For each identified spend endpoint, add at the top of the function/method:

```python
from world.magic.services import has_pending_alterations

# In the spend function, before any spending logic:
if has_pending_alterations(character_sheet):
    raise AlterationGateError
```

`AlterationGateError` is already defined in `src/world/magic/types.py` (Task 1). Import it:

```python
from world.magic.types import AlterationGateError
```

The implementer should grep for spend endpoints during implementation:
```
grep -rn "spend_xp\|claim_kudos\|add_distinction" src/world/progression/ src/world/distinctions/
```
and add the gate check to each. Write a test per endpoint verifying the error is raised.

- [ ] **Step 4: Run affected test suites**

```
arx test world.magic world.progression world.distinctions --keepdb
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add src/world/magic/tests/test_alteration_gate.py src/world/magic/types.py
git add <modified spend endpoint files>
git commit -m "feat(magic): add progression gate for pending alterations"
```

---

## Task 9: Serializers

**Files:**
- Modify: `src/world/magic/serializers.py`

- [ ] **Step 1: Add serializers**

Add to `src/world/magic/serializers.py`:

```python
from rest_framework import serializers

from world.magic.constants import ALTERATION_TIER_CAPS, AlterationTier
from world.magic.models import (
    MagicalAlterationEvent,
    MagicalAlterationTemplate,
    PendingAlteration,
)


class PendingAlterationSerializer(serializers.ModelSerializer):
    """Read-only serializer for pending alterations shown on character sheet."""

    origin_affinity_name = serializers.CharField(
        source="origin_affinity.name", read_only=True,
    )
    origin_resonance_name = serializers.CharField(
        source="origin_resonance.name", read_only=True,
    )
    tier_display = serializers.CharField(
        source="get_tier_display", read_only=True,
    )
    tier_caps = serializers.SerializerMethodField()

    class Meta:
        model = PendingAlteration
        fields = [
            "id", "status", "tier", "tier_display", "tier_caps",
            "origin_affinity_name", "origin_resonance_name",
            "triggering_scene", "created_at",
        ]

    def get_tier_caps(self, obj: PendingAlteration) -> dict:
        return ALTERATION_TIER_CAPS.get(obj.tier, {})


class LibraryEntrySerializer(serializers.ModelSerializer):
    """Read-only serializer for library browse cards."""

    name = serializers.CharField(
        source="condition_template.name", read_only=True,
    )
    player_description = serializers.CharField(
        source="condition_template.player_description", read_only=True,
    )
    observer_description = serializers.CharField(
        source="condition_template.observer_description", read_only=True,
    )
    origin_affinity_name = serializers.CharField(
        source="origin_affinity.name", read_only=True,
    )

    class Meta:
        model = MagicalAlterationTemplate
        fields = [
            "id", "name", "tier", "player_description",
            "observer_description", "origin_affinity_name",
            "weakness_magnitude", "resonance_bonus_magnitude",
            "social_reactivity_magnitude", "is_visible_at_rest",
        ]


class AlterationResolutionSerializer(serializers.Serializer):
    """Write serializer for resolving a PendingAlteration."""

    # Use-as-is path
    library_template_id = serializers.IntegerField(required=False)

    # Author-from-scratch path
    name = serializers.CharField(max_length=60, min_length=3, required=False)
    player_description = serializers.CharField(required=False)
    observer_description = serializers.CharField(required=False)
    weakness_damage_type_id = serializers.IntegerField(
        required=False, allow_null=True,
    )
    weakness_magnitude = serializers.IntegerField(
        min_value=0, default=0,
    )
    resonance_bonus_magnitude = serializers.IntegerField(
        min_value=0, default=0,
    )
    social_reactivity_magnitude = serializers.IntegerField(
        min_value=0, default=0,
    )
    is_visible_at_rest = serializers.BooleanField(default=False)
    parent_template_id = serializers.IntegerField(
        required=False, allow_null=True,
    )

    def validate(self, attrs):
        """Run tier schema validation against the pending's constraints."""
        from world.magic.services import validate_alteration_resolution  # noqa: PLC0415

        pending = self.context["pending"]
        is_staff = self.context["request"].user.is_staff

        # If library template, validate library entry exists and no duplicate
        if "library_template_id" in attrs:
            library_errors = validate_alteration_resolution(
                pending_tier=pending.tier,
                pending_affinity_id=pending.origin_affinity_id,
                pending_resonance_id=pending.origin_resonance_id,
                payload={"library_entry_pk": attrs["library_template_id"]},
                is_staff=is_staff,
                character_sheet=self.context.get("character_sheet"),
            )
            if library_errors:
                raise serializers.ValidationError(library_errors)
            return attrs

        # Author-from-scratch: inject tier + origin from pending (not client-supplied)
        payload = {
            "tier": pending.tier,
            "origin_affinity_id": pending.origin_affinity_id,
            "origin_resonance_id": pending.origin_resonance_id,
            **attrs,
        }
        errors = validate_alteration_resolution(
            pending_tier=pending.tier,
            pending_affinity_id=pending.origin_affinity_id,
            pending_resonance_id=pending.origin_resonance_id,
            payload=payload,
            is_staff=is_staff,
            character_sheet=self.context.get("character_sheet"),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
```

- [ ] **Step 2: Commit**

```
git add src/world/magic/serializers.py
git commit -m "feat(magic): add alteration serializers"
```

---

## Task 10: API ViewSet

**Files:**
- Modify: `src/world/magic/views.py`
- Modify: `src/world/magic/urls.py`
- Create: `src/world/magic/tests/test_alteration_views.py`

- [ ] **Step 1: Write failing API tests**

Create `src/world/magic/tests/test_alteration_views.py`:

```python
"""Tests for alteration API endpoints."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import AlterationTier, MIN_ALTERATION_DESCRIPTION_LENGTH, PendingAlterationStatus
from world.magic.factories import (
    AffinityFactory,
    MagicalAlterationTemplateFactory,
    PendingAlterationFactory,
    ResonanceFactory,
)


class PendingAlterationViewSetTests(BaseEvenniaTest):
    """Test the PendingAlteration API."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)

    def setUp(self):
        # Authenticate as the character's player
        account = self.sheet.character.account
        if account:
            self.client.force_login(account)

    def test_list_pending_alterations(self):
        """GET returns the character's open pending alterations."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        url = reverse("magic:pending-alteration-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_resolve_author_from_scratch(self):
        """POST resolve action creates template and applies condition."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )
        url = reverse(
            "magic:pending-alteration-resolve",
            args=[pending.pk],
        )
        response = self.client.post(url, {
            "name": "Voice of Many",
            "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "weakness_magnitude": 1,
            "resonance_bonus_magnitude": 1,
            "social_reactivity_magnitude": 1,
            "is_visible_at_rest": False,
        })
        assert response.status_code == status.HTTP_200_OK
        pending.refresh_from_db()
        assert pending.status == PendingAlterationStatus.RESOLVED

    def test_library_browse(self):
        """GET library action returns tier-matched library entries."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )
        MagicalAlterationTemplateFactory(
            tier=AlterationTier.MARKED,
            is_library_entry=True,
        )
        MagicalAlterationTemplateFactory(
            tier=AlterationTier.TOUCHED,  # wrong tier
            is_library_entry=True,
        )
        url = reverse(
            "magic:pending-alteration-library",
            args=[pending.pk],
        )
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1  # only tier-matched entry
```

Note: URL names (`magic:pending-alteration-list`, etc.) depend on how the router registers the viewset. Adapt during implementation based on the existing `urls.py` pattern.

- [ ] **Step 2: Run tests to verify they fail**

```
arx test world.magic.tests.test_alteration_views --keepdb
```
Expected: failures from missing viewset/urls.

- [ ] **Step 3: Implement the viewset**

Add to `src/world/magic/views.py`:

```python
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin

from world.stories.pagination import StandardResultsSetPagination

from world.magic.models import MagicalAlterationTemplate, PendingAlteration
from world.magic.serializers import (
    AlterationResolutionSerializer,
    LibraryEntrySerializer,
    PendingAlterationSerializer,
)
from world.magic.services import get_library_entries, resolve_pending_alteration


class PendingAlterationViewSet(
    ListModelMixin, RetrieveModelMixin, GenericViewSet,
):
    """ViewSet for pending magical alterations.

    list: Returns the authenticated player's open pending alterations.
    retrieve: Returns a single pending alteration.
    resolve: Custom action to resolve a pending via author or library.
    library: Custom action to browse tier-matched library entries.
    """

    serializer_class = PendingAlterationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filterset_fields = ["status", "tier"]

    def get_queryset(self):
        # Filter to the requesting player's character's pendings
        # Adapt based on how the project resolves request → CharacterSheet
        return PendingAlteration.objects.filter(
            character__character__account=self.request.user,
        ).select_related(
            "origin_affinity", "origin_resonance", "triggering_scene",
        )

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Resolve a pending alteration."""
        pending = self.get_object()
        serializer = AlterationResolutionSerializer(
            data=request.data,
            context={
                "pending": pending,
                "request": request,
                "character_sheet": pending.character,
            },
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Dispatch to library or author path
        library_id = data.get("library_template_id")
        if library_id:
            library_template = MagicalAlterationTemplate.objects.get(
                pk=library_id, is_library_entry=True,
            )
            result = resolve_pending_alteration(
                pending=pending,
                name=library_template.condition_template.name,
                player_description=library_template.condition_template.player_description,
                observer_description=library_template.condition_template.observer_description,
                weakness_magnitude=library_template.weakness_magnitude,
                resonance_bonus_magnitude=library_template.resonance_bonus_magnitude,
                social_reactivity_magnitude=library_template.social_reactivity_magnitude,
                is_visible_at_rest=library_template.is_visible_at_rest,
                resolved_by=request.user,
                library_template=library_template,
            )
        else:
            from world.conditions.models import DamageType  # noqa: PLC0415

            weakness_dt_id = data.get("weakness_damage_type_id")
            weakness_dt = (
                DamageType.objects.get(pk=weakness_dt_id)
                if weakness_dt_id
                else None
            )
            parent_id = data.get("parent_template_id")
            parent = (
                MagicalAlterationTemplate.objects.get(pk=parent_id)
                if parent_id
                else None
            )

            result = resolve_pending_alteration(
                pending=pending,
                name=data["name"],
                player_description=data["player_description"],
                observer_description=data["observer_description"],
                weakness_damage_type=weakness_dt,
                weakness_magnitude=data.get("weakness_magnitude", 0),
                resonance_bonus_magnitude=data.get("resonance_bonus_magnitude", 0),
                social_reactivity_magnitude=data.get("social_reactivity_magnitude", 0),
                is_visible_at_rest=data.get("is_visible_at_rest", False),
                resolved_by=request.user,
                parent_template=parent,
            )

        return Response(
            {"status": "resolved", "event_id": result.event.pk},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def library(self, request, pk=None):
        """Browse tier-matched library entries for a pending alteration."""
        pending = self.get_object()
        entries = get_library_entries(
            tier=pending.tier,
            character_affinity_id=pending.origin_affinity_id,
        )
        serializer = LibraryEntrySerializer(entries, many=True)
        return Response(serializer.data)
```

Add `get_library_entries` to `services.py`:

```python
def get_library_entries(
    *, tier: int, character_affinity_id: int | None = None,
) -> "QuerySet[MagicalAlterationTemplate]":
    """Return library entries matching the given tier.

    Sorted: matching origin_affinity first, then matching origin_resonance,
    then everything else (per spec Section 5).
    """
    from django.db.models import Case, Value, When  # noqa: PLC0415

    qs = MagicalAlterationTemplate.objects.filter(
        is_library_entry=True,
        tier=tier,
    ).select_related(
        "condition_template",
        "origin_affinity",
        "origin_resonance",
    )
    if character_affinity_id is not None:
        qs = qs.annotate(
            affinity_match=Case(
                When(origin_affinity_id=character_affinity_id, then=Value(0)),
                default=Value(1),
            ),
        ).order_by("affinity_match", "condition_template__name")
    return qs
```

- [ ] **Step 4: Register the viewset in urls.py**

Add to `src/world/magic/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from world.magic.views import PendingAlterationViewSet

router = DefaultRouter()
router.register(
    r"pending-alterations",
    PendingAlterationViewSet,
    basename="pending-alteration",
)

# Add router.urls to urlpatterns
```

Check the existing `urls.py` pattern in the magic app and follow it.

- [ ] **Step 5: Run view tests**

```
arx test world.magic.tests.test_alteration_views --keepdb
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```
git add src/world/magic/views.py src/world/magic/urls.py src/world/magic/serializers.py src/world/magic/services.py src/world/magic/tests/test_alteration_views.py
git commit -m "feat(magic): add PendingAlterationViewSet with resolve and library actions"
```

---

## Task 11: Integration Tests

**Files:**
- Modify: `src/integration_tests/game_content/magic.py`
- Create: `src/integration_tests/pipeline/test_alteration_pipeline.py`

- [ ] **Step 1: Add alteration content to `MagicContent`**

Add to `src/integration_tests/game_content/magic.py` a method that creates:
- 2-3 staff library entries at different tiers with full condition effect rows
- A Soulfray stage consequence pool with a `MAGICAL_SCARS` entry

Follow the existing `MagicContent` pattern in that file.

- [ ] **Step 2: Write integration tests**

Create `src/integration_tests/pipeline/test_alteration_pipeline.py`:

```python
"""End-to-end integration tests for the magical alteration pipeline.

Tests the full flow: technique use → Soulfray → MAGICAL_SCARS consequence →
PendingAlteration → player resolution → ConditionInstance applied.
"""

# Follow the existing integration test patterns in
# src/integration_tests/pipeline/. Key tests:
#
# 1. Core flow: character overburns → MAGICAL_SCARS fires →
#    PendingAlteration created → resolve via author-from-scratch →
#    condition applied + event created + gate released
#
# 2. Same-scene escalation: two overburns in one scene →
#    single PendingAlteration at higher tier
#
# 3. Library browse: seed library entries → query returns only
#    tier-matched → use-as-is resolves correctly
#
# See spec Section 6 (Testing Strategy) for full test list.
```

The implementer should flesh out these tests following the existing pipeline test patterns. The key is driving the full pipeline through `use_technique()` → consequence selection → handler → pending → resolution, using factories from `game_content/magic.py`.

- [ ] **Step 3: Run integration tests**

```
arx test integration_tests.pipeline.test_alteration_pipeline --keepdb
```
Expected: all tests pass.

- [ ] **Step 4: Run full regression on affected suites**

```
arx test world.magic world.mechanics world.conditions world.progression --keepdb
```
Expected: all tests pass with no regressions.

- [ ] **Step 5: Commit**

```
git add src/integration_tests/game_content/magic.py src/integration_tests/pipeline/test_alteration_pipeline.py
git commit -m "test(magic): add alteration pipeline integration tests"
```

---

## Task 12: Final Cleanup and Roadmap Update

**Files:**
- Modify: `docs/roadmap/magic.md`

- [ ] **Step 1: Update Scope 5 status in roadmap**

Change `**Scope #5 — Magical Alteration Resolution (TODO):**` to `**Scope #5 — Magical Alteration Resolution (DONE):**` and add a "What was built" summary following the pattern of Scopes 1-4.

- [ ] **Step 2: Final regression test**

```
arx test world.magic world.mechanics world.conditions world.progression world.checks --keepdb
```

- [ ] **Step 3: Commit**

```
git add docs/roadmap/magic.md
git commit -m "docs: mark Scope 5 (Magical Alteration Resolution) as complete"
```
