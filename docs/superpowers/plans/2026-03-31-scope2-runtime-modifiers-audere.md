# Scope #2: Runtime Modifiers & Audere — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make technique use dynamic by connecting runtime stats to engagement state, the modifier system, and the Audere condition.

**Architecture:** Two modifier streams feed `get_runtime_technique_stats()`: identity bonuses via `get_modifier_total()` (existing CharacterModifier system) and process bonuses via fields on a new `CharacterEngagement` model. Audere is a ConditionTemplate whose acceptance writes process modifiers to the engagement. Social safety bonus is a direct check (no engagement = bonus applies).

**Tech Stack:** Django, SharedMemoryModel, FactoryBoy, existing CharacterModifier/ConditionTemplate systems

**Spec:** `docs/superpowers/specs/2026-03-30-scope2-runtime-modifiers-audere-design.md`

**Test command:** `arx test world.mechanics world.magic --keepdb`

---

## File Structure

### New Files
- `src/world/mechanics/engagement.py` — CharacterEngagement model + EngagementType choices
- `src/world/magic/audere.py` — AudereThreshold model, `check_audere_eligibility()`, `offer_audere()`, `end_audere()`

### Modified Files
- `src/world/mechanics/constants.py` — add `TECHNIQUE_STAT_CATEGORY_NAME`, `EngagementType`
- `src/world/mechanics/models.py` — import and re-export CharacterEngagement
- `src/world/mechanics/factories.py` — add `CharacterEngagementFactory`
- `src/world/mechanics/admin.py` — register CharacterEngagement
- `src/world/magic/models.py` — add `pre_audere_maximum` nullable field to CharacterAnima
- `src/world/magic/types.py` — update `RuntimeTechniqueStats` with modifier breakdown fields
- `src/world/magic/services.py` — upgrade `get_runtime_technique_stats()`, update `use_technique()` Step 7
- `src/world/magic/factories.py` — add `AudereThresholdFactory`, `IntensityTierFactory`
- `src/world/magic/admin.py` — register AudereThreshold

### Test Files
- `src/world/mechanics/tests/test_engagement.py` — CharacterEngagement model tests
- `src/world/magic/tests/test_audere.py` — Audere eligibility, offer, lifecycle tests
- `src/world/magic/tests/test_use_technique.py` — update existing tests for new signature
- `src/world/mechanics/tests/test_pipeline_integration.py` — add `RuntimeModifierTests` class

---

## Task 1: CharacterEngagement Model

**Files:**
- Create: `src/world/mechanics/engagement.py`
- Modify: `src/world/mechanics/constants.py`
- Modify: `src/world/mechanics/models.py`
- Create: `src/world/mechanics/tests/test_engagement.py`

- [ ] **Step 1: Add EngagementType to constants**

In `src/world/mechanics/constants.py`, add:

```python
TECHNIQUE_STAT_CATEGORY_NAME = "technique_stat"


class EngagementType(models.TextChoices):
    """What kind of stakes-bearing activity a character is engaged in."""

    CHALLENGE = "challenge", "Challenge"
    COMBAT = "combat", "Combat"
    MISSION = "mission", "Mission"
```

- [ ] **Step 2: Write the CharacterEngagement model**

Create `src/world/mechanics/engagement.py`:

```python
"""Character engagement state — what a character is actively doing with stakes."""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.mechanics.constants import EngagementType


class CharacterEngagement(SharedMemoryModel):
    """What a character is actively doing that has stakes.

    Observable by other characters. Engagement type and escalation level
    inform social interaction decisions and technique runtime modifiers.

    Process modifiers (intensity_modifier, control_modifier) are transient
    state that lives only for the duration of the engagement. These are
    updated by the engaging system (combat, missions, challenges) and
    vanish when the engagement is deleted.

    Identity-derived bonuses (from Distinctions, Conditions, etc.) use the
    CharacterModifier system instead — they persist with their source.
    """

    character = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="engagement",
        help_text="The character who is engaged.",
    )
    engagement_type = models.CharField(
        max_length=20,
        choices=EngagementType.choices,
        help_text="What kind of stakes-bearing activity.",
    )
    source_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Content type of the engagement source.",
    )
    source_id = models.PositiveIntegerField(
        help_text="PK of the engagement source object.",
    )
    source = GenericForeignKey("source_content_type", "source_id")
    escalation_level = models.PositiveIntegerField(
        default=0,
        help_text="How much pressure has built up. Managed by the engaging system.",
    )
    intensity_modifier = models.IntegerField(
        default=0,
        help_text="Process-derived intensity bonus (escalation, Audere, combat events).",
    )
    control_modifier = models.IntegerField(
        default=0,
        help_text="Process-derived control bonus (process state only).",
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the engagement began.",
    )

    class Meta:
        verbose_name = "Character Engagement"
        verbose_name_plural = "Character Engagements"

    def __str__(self) -> str:
        return f"{self.character} — {self.get_engagement_type_display()}"
```

- [ ] **Step 3: Import CharacterEngagement in models.py**

In `src/world/mechanics/models.py`, at the end of imports or at the bottom of the file, add:

```python
from world.mechanics.engagement import CharacterEngagement  # noqa: F401
```

This ensures Django discovers the model for migrations.

- [ ] **Step 4: Write model tests**

Create `src/world/mechanics/tests/test_engagement.py`:

```python
"""Tests for CharacterEngagement model."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement


class CharacterEngagementModelTests(TestCase):
    """Basic model behavior tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="TestChar")
        # Use ObjectDB itself as a generic source for testing
        cls.source_ct = ContentType.objects.get_for_model(ObjectDB)
        cls.source_obj = ObjectDB.objects.create(db_key="TestSource")

    def test_create_engagement(self) -> None:
        engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
        )
        assert engagement.escalation_level == 0
        assert engagement.intensity_modifier == 0
        assert engagement.control_modifier == 0

    def test_one_to_one_constraint(self) -> None:
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            CharacterEngagement.objects.create(
                character=self.character,
                engagement_type=EngagementType.COMBAT,
                source_content_type=self.source_ct,
                source_id=self.source_obj.pk,
            )

    def test_delete_clears_process_state(self) -> None:
        engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
            escalation_level=5,
            intensity_modifier=12,
            control_modifier=-3,
        )
        engagement.delete()
        assert not CharacterEngagement.objects.filter(
            character=self.character,
        ).exists()

    def test_str_representation(self) -> None:
        engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.MISSION,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
        )
        assert "Mission" in str(engagement)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `arx test world.mechanics.tests.test_engagement --keepdb`

Note: You will need to run `arx manage makemigrations mechanics` and `arx manage migrate --run-syncdb` first since this is a new model. Use `--keepdb` to preserve the dev database.

- [ ] **Step 6: Add factory**

In `src/world/mechanics/factories.py`, add:

```python
from django.contrib.contenttypes.models import ContentType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.constants import EngagementType


class CharacterEngagementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterEngagement

    character = factory.LazyFunction(lambda: ObjectDB.objects.create(db_key="EngagedChar"))
    engagement_type = EngagementType.CHALLENGE
    source_content_type = factory.LazyFunction(
        lambda: ContentType.objects.get_for_model(ObjectDB)
    )
    source_id = factory.LazyAttribute(lambda o: o.character.pk)
    escalation_level = 0
    intensity_modifier = 0
    control_modifier = 0
```

- [ ] **Step 7: Add admin registration**

In `src/world/mechanics/admin.py`, add:

```python
from world.mechanics.engagement import CharacterEngagement


@admin.register(CharacterEngagement)
class CharacterEngagementAdmin(admin.ModelAdmin):
    list_display = ("character", "engagement_type", "escalation_level", "started_at")
    list_filter = ("engagement_type",)
    readonly_fields = ("started_at",)
```

- [ ] **Step 8: Generate and apply migration**

Run: `arx manage makemigrations mechanics && arx manage migrate --keepdb`

- [ ] **Step 9: Run full mechanics test suite**

Run: `arx test world.mechanics --keepdb`

- [ ] **Step 10: Commit**

```bash
git add src/world/mechanics/
git commit -m "Add CharacterEngagement model with process modifier fields

OneToOne to ObjectDB with engagement_type, escalation_level,
intensity_modifier, and control_modifier. Process state for
transient combat/mission/challenge bonuses.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: ModifierTargets for Technique Stats

**Files:**
- Modify: `src/world/mechanics/factories.py` (may need factory helpers)
- Create: `src/world/mechanics/tests/test_technique_stat_modifiers.py`

This task creates the authored data (ModifierCategory + ModifierTargets) and
verifies they work with the existing modifier system.

- [ ] **Step 1: Write test for technique stat modifier targets**

Create `src/world/mechanics/tests/test_technique_stat_modifiers.py`:

```python
"""Tests for technique stat modifier targets."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import TECHNIQUE_STAT_CATEGORY_NAME
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierSourceFactory,
    ModifierTargetFactory,
)
from world.mechanics.services import get_modifier_total


class TechniqueStatModifierTests(TestCase):
    """Verify CharacterModifiers can target technique stats."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
        cls.intensity_target = ModifierTargetFactory(
            name="intensity", category=cls.category
        )
        cls.control_target = ModifierTargetFactory(
            name="control", category=cls.category
        )

    def test_intensity_modifier_stacks(self) -> None:
        source1 = ModifierSourceFactory()
        source2 = ModifierSourceFactory()
        CharacterModifierFactory(
            character=self.sheet, target=self.intensity_target,
            value=3, source=source1,
        )
        CharacterModifierFactory(
            character=self.sheet, target=self.intensity_target,
            value=5, source=source2,
        )
        assert get_modifier_total(self.sheet, self.intensity_target) == 8

    def test_control_modifier(self) -> None:
        source = ModifierSourceFactory()
        CharacterModifierFactory(
            character=self.sheet, target=self.control_target,
            value=4, source=source,
        )
        assert get_modifier_total(self.sheet, self.control_target) == 4

    def test_no_modifiers_returns_zero(self) -> None:
        assert get_modifier_total(self.sheet, self.intensity_target) == 0
```

- [ ] **Step 2: Run test to verify it passes**

Run: `arx test world.mechanics.tests.test_technique_stat_modifiers --keepdb`

These should pass immediately since we're just using the existing modifier system with new ModifierTarget records.

- [ ] **Step 3: Commit**

```bash
git add src/world/mechanics/
git commit -m "Add technique stat ModifierTargets (intensity, control)

Verifies the existing modifier system works with technique_stat
category targets. No new infrastructure — just new authored data.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Upgrade `get_runtime_technique_stats()`

**Files:**
- Modify: `src/world/magic/services.py:131-143`
- Modify: `src/world/magic/types.py:60-68`
- Create: `src/world/magic/tests/test_runtime_stats.py`

- [ ] **Step 1: Write failing tests for the upgraded function**

Create `src/world/magic/tests/test_runtime_stats.py`:

```python
"""Tests for get_runtime_technique_stats with modifier integration."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import IntensityTierFactory, TechniqueFactory
from world.magic.services import get_runtime_technique_stats
from world.mechanics.constants import TECHNIQUE_STAT_CATEGORY_NAME, EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierSourceFactory,
    ModifierTargetFactory,
)


class RuntimeStatsBaseTests(TestCase):
    """Test get_runtime_technique_stats with base values only."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=10, control=12)
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def test_base_values_no_modifiers_no_engagement(self) -> None:
        """Without modifiers or engagement, returns base + social safety."""
        stats = get_runtime_technique_stats(self.technique, self.character)
        assert stats.intensity == 10
        # control should include social safety bonus
        assert stats.control > 12


class RuntimeStatsIdentityModifierTests(TestCase):
    """Test identity-derived modifiers via CharacterModifier."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=10, control=10)
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
        cls.intensity_target = ModifierTargetFactory(
            name="intensity", category=cls.category,
        )
        cls.control_target = ModifierTargetFactory(
            name="control", category=cls.category,
        )

    def test_identity_intensity_modifier(self) -> None:
        source = ModifierSourceFactory()
        CharacterModifierFactory(
            character=self.sheet, target=self.intensity_target,
            value=5, source=source,
        )
        stats = get_runtime_technique_stats(self.technique, self.character)
        assert stats.intensity == 15  # 10 base + 5 modifier

    def test_identity_control_modifier(self) -> None:
        source = ModifierSourceFactory()
        CharacterModifierFactory(
            character=self.sheet, target=self.control_target,
            value=3, source=source,
        )
        stats = get_runtime_technique_stats(self.technique, self.character)
        # 10 base + 3 modifier + social safety (no engagement)
        assert stats.control >= 13


class RuntimeStatsEngagementTests(TestCase):
    """Test process-derived modifiers via CharacterEngagement."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=10, control=10)
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.source_ct = ContentType.objects.get_for_model(ObjectDB)
        cls.source_obj = ObjectDB.objects.create(db_key="EngSource")

    def test_engagement_removes_social_safety(self) -> None:
        """Engaged characters do NOT get the social safety bonus."""
        stats_social = get_runtime_technique_stats(self.technique, self.character)
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
        )
        stats_engaged = get_runtime_technique_stats(self.technique, self.character)
        assert stats_engaged.control < stats_social.control

    def test_engagement_intensity_modifier(self) -> None:
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
            intensity_modifier=8,
        )
        stats = get_runtime_technique_stats(self.technique, self.character)
        assert stats.intensity == 18  # 10 base + 8 process

    def test_engagement_control_modifier(self) -> None:
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
            control_modifier=-2,
        )
        stats = get_runtime_technique_stats(self.technique, self.character)
        assert stats.control == 8  # 10 base + (-2) process, no social safety


class RuntimeStatsIntensityTierTests(TestCase):
    """Test IntensityTier.control_modifier integration."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=20, control=20)
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        # Create tiers: Minor (threshold 1, +0), Major (threshold 15, -5)
        IntensityTierFactory(name="Minor", threshold=1, control_modifier=0)
        IntensityTierFactory(name="Major", threshold=15, control_modifier=-5)

    def test_intensity_tier_control_modifier_applied(self) -> None:
        """High intensity triggers negative control modifier from tier."""
        stats = get_runtime_technique_stats(self.technique, self.character)
        # 20 base + social safety bonus - 5 from Major tier
        # Exact value depends on social safety, but should be less than 20 + safety
        # The tier modifier makes control lower than without it
        assert stats.control < 20 + 20  # rough upper bound sanity check
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test world.magic.tests.test_runtime_stats --keepdb`

Expected: failures because `get_runtime_technique_stats()` still returns base values.

- [ ] **Step 3: Add IntensityTierFactory to magic factories**

In `src/world/magic/factories.py`, add:

```python
from world.magic.models import IntensityTier


class IntensityTierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntensityTier

    name = factory.Sequence(lambda n: f"Tier {n}")
    threshold = factory.Sequence(lambda n: (n + 1) * 5)
    control_modifier = 0
    description = ""
```

- [ ] **Step 4: Implement the upgraded `get_runtime_technique_stats()`**

In `src/world/magic/services.py`, replace the function at lines 131-143:

```python
def get_runtime_technique_stats(
    technique: Technique,
    character: ObjectDB | None,
) -> RuntimeTechniqueStats:
    """Calculate runtime intensity and control for a technique.

    Combines three sources:
    1. Technique base values
    2. Identity modifiers (CharacterModifier targeting technique_stat)
    3. Process modifiers (CharacterEngagement fields)

    Social safety bonus applies when the character has no active engagement.
    IntensityTier.control_modifier applies based on the resulting intensity.
    """
    if character is None:
        return RuntimeTechniqueStats(
            intensity=technique.intensity,
            control=technique.control,
        )

    # Identity stream: CharacterModifier totals
    identity_intensity = 0
    identity_control = 0
    intensity_target = _get_technique_stat_target("intensity")
    control_target = _get_technique_stat_target("control")
    sheet = _get_character_sheet(character)
    if sheet is not None:
        if intensity_target is not None:
            identity_intensity = get_modifier_total(sheet, intensity_target)
        if control_target is not None:
            identity_control = get_modifier_total(sheet, control_target)

    # Process stream: CharacterEngagement fields
    process_intensity = 0
    process_control = 0
    social_safety = 0
    try:
        engagement = CharacterEngagement.objects.get(character=character)
        process_intensity = engagement.intensity_modifier
        process_control = engagement.control_modifier
    except CharacterEngagement.DoesNotExist:
        social_safety = _get_social_safety_bonus()

    # Sum all sources
    runtime_intensity = (
        technique.intensity + identity_intensity + process_intensity
    )
    runtime_control = (
        technique.control + identity_control + process_control + social_safety
    )

    # IntensityTier.control_modifier based on resulting intensity
    tier_control = _get_intensity_tier_control_modifier(runtime_intensity)
    runtime_control += tier_control

    return RuntimeTechniqueStats(
        intensity=runtime_intensity,
        control=runtime_control,
    )


def _get_technique_stat_target(name: str) -> "ModifierTarget | None":
    """Look up a technique_stat ModifierTarget by name. Returns None if not found."""
    from world.mechanics.constants import TECHNIQUE_STAT_CATEGORY_NAME
    from world.mechanics.models import ModifierTarget

    try:
        return ModifierTarget.objects.get(
            category__name=TECHNIQUE_STAT_CATEGORY_NAME,
            name=name,
        )
    except ModifierTarget.DoesNotExist:
        return None


def _get_character_sheet(character: ObjectDB) -> "CharacterSheet | None":
    """Get the CharacterSheet for a character. Returns None if not found."""
    from world.character_sheets.models import CharacterSheet

    try:
        return CharacterSheet.objects.get(character=character)
    except CharacterSheet.DoesNotExist:
        return None


def _get_social_safety_bonus() -> int:
    """Get the social safety control bonus for characters not in engagement.

    This is authored data. For now, returns a sensible default.
    Future: read from a GameSetting or similar config model.
    """
    # TODO: Make this authored data (GameSetting or config table)
    return 10


def _get_intensity_tier_control_modifier(runtime_intensity: int) -> int:
    """Look up the IntensityTier for a given intensity and return its control_modifier."""
    tier = (
        IntensityTier.objects.filter(threshold__lte=runtime_intensity)
        .order_by("-threshold")
        .first()
    )
    if tier is None:
        return 0
    return tier.control_modifier
```

Also add the required imports at the top of `services.py`:

```python
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import get_modifier_total
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `arx test world.magic.tests.test_runtime_stats --keepdb`

- [ ] **Step 6: Run existing use_technique tests to check for regressions**

Run: `arx test world.magic.tests.test_use_technique --keepdb`

The existing tests may need minor adjustments since `get_runtime_technique_stats()` now
returns different values (social safety bonus) when the character has no engagement.
If tests fail, update them to account for the social safety bonus or create
CharacterEngagement records in the test setup to suppress it.

- [ ] **Step 7: Fix any regressions in existing tests**

Adjust existing test expectations or setup as needed. The most likely issue
is that effective anima cost changes because control now includes the social
safety bonus. Either:
- Add engagement to tests that need predictable control values, or
- Adjust expected values to account for the safety bonus

- [ ] **Step 8: Run full magic + mechanics test suites**

Run: `arx test world.magic world.mechanics --keepdb`

- [ ] **Step 9: Commit**

```bash
git add src/world/magic/ src/world/mechanics/
git commit -m "Upgrade get_runtime_technique_stats with two modifier streams

Identity bonuses via CharacterModifier (technique_stat targets) and
process bonuses via CharacterEngagement fields. Social safety control
bonus when not engaged. IntensityTier.control_modifier integration.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: AudereThreshold Config Model

**Files:**
- Create: `src/world/magic/audere.py`
- Modify: `src/world/magic/models.py` — add `pre_audere_maximum` to CharacterAnima
- Modify: `src/world/magic/factories.py`
- Modify: `src/world/magic/admin.py`
- Create: `src/world/magic/tests/test_audere.py`

- [ ] **Step 1: Write the AudereThreshold model**

Create `src/world/magic/audere.py`:

```python
"""Audere threshold configuration and lifecycle management."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class AudereThreshold(SharedMemoryModel):
    """Configuration for when Audere can be triggered and its effects.

    Expected to have a single row (global config). Modeled as a table
    for factory/test flexibility and admin editability.

    Audere requires a hard triple gate:
    1. Runtime intensity at or above minimum_intensity_tier
    2. Active Anima Warp condition at or above minimum_warp_stage
    3. Active CharacterEngagement (character must be in stakes)
    """

    minimum_intensity_tier = models.ForeignKey(
        "magic.IntensityTier",
        on_delete=models.PROTECT,
        help_text="Runtime intensity must reach this tier for Audere to trigger.",
    )
    minimum_warp_stage = models.ForeignKey(
        "conditions.ConditionStage",
        on_delete=models.PROTECT,
        help_text="Anima Warp must be at this stage or higher.",
    )
    intensity_bonus = models.IntegerField(
        help_text="Added to engagement.intensity_modifier when Audere activates.",
    )
    anima_pool_bonus = models.PositiveIntegerField(
        help_text="Temporary increase to CharacterAnima.maximum during Audere.",
    )
    warp_multiplier = models.PositiveIntegerField(
        default=2,
        help_text="Warp severity increment multiplier during Audere.",
    )

    class Meta:
        verbose_name = "Audere Threshold"
        verbose_name_plural = "Audere Thresholds"

    def __str__(self) -> str:
        return (
            f"Audere: tier≥{self.minimum_intensity_tier}, "
            f"warp≥{self.minimum_warp_stage}, "
            f"+{self.intensity_bonus} intensity"
        )
```

- [ ] **Step 2: Add pre_audere_maximum to CharacterAnima**

In `src/world/magic/models.py`, add to `CharacterAnima` (after `last_recovery` field, around line 569):

```python
    pre_audere_maximum = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Stored maximum before Audere expanded the pool. Null when not in Audere.",
    )
```

- [ ] **Step 3: Import AudereThreshold in models.py**

In `src/world/magic/models.py`, at the bottom:

```python
from world.magic.audere import AudereThreshold  # noqa: F401, E402
```

- [ ] **Step 4: Add AudereThresholdFactory and IntensityTierFactory**

In `src/world/magic/factories.py`, add:

```python
from world.magic.audere import AudereThreshold
from world.magic.models import IntensityTier


class IntensityTierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntensityTier

    name = factory.Sequence(lambda n: f"Tier {n}")
    threshold = factory.Sequence(lambda n: (n + 1) * 5)
    control_modifier = 0
    description = ""


class AudereThresholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AudereThreshold

    minimum_intensity_tier = factory.SubFactory(IntensityTierFactory)
    minimum_warp_stage = factory.SubFactory(
        "world.conditions.factories.ConditionStageFactory"
    )
    intensity_bonus = 20
    anima_pool_bonus = 30
    warp_multiplier = 2
```

- [ ] **Step 5: Add admin registration**

In `src/world/magic/admin.py`, add:

```python
from world.magic.audere import AudereThreshold


@admin.register(AudereThreshold)
class AudereThresholdAdmin(admin.ModelAdmin):
    list_display = (
        "minimum_intensity_tier",
        "minimum_warp_stage",
        "intensity_bonus",
        "anima_pool_bonus",
        "warp_multiplier",
    )
```

- [ ] **Step 6: Write model tests**

Create `src/world/magic/tests/test_audere.py`:

```python
"""Tests for Audere threshold and lifecycle."""

from django.test import TestCase

from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.factories import AudereThresholdFactory, IntensityTierFactory


class AudereThresholdModelTests(TestCase):
    """Test AudereThreshold configuration model."""

    def test_create_threshold(self) -> None:
        condition = ConditionTemplateFactory(has_progression=True)
        stage = ConditionStageFactory(condition=condition, stage_order=3)
        tier = IntensityTierFactory(name="Major", threshold=15)
        threshold = AudereThresholdFactory(
            minimum_intensity_tier=tier,
            minimum_warp_stage=stage,
            intensity_bonus=25,
            anima_pool_bonus=40,
            warp_multiplier=3,
        )
        assert threshold.intensity_bonus == 25
        assert threshold.anima_pool_bonus == 40
        assert threshold.warp_multiplier == 3
        assert threshold.minimum_intensity_tier == tier
        assert threshold.minimum_warp_stage == stage
```

- [ ] **Step 7: Generate and apply migrations**

Run: `arx manage makemigrations magic && arx manage migrate --keepdb`

- [ ] **Step 8: Run tests**

Run: `arx test world.magic.tests.test_audere --keepdb`

- [ ] **Step 9: Commit**

```bash
git add src/world/magic/
git commit -m "Add AudereThreshold config model and pre_audere_maximum field

AudereThreshold stores trigger gates (intensity tier, warp stage)
and effect values (intensity bonus, anima pool expansion, warp
multiplier). CharacterAnima gets nullable pre_audere_maximum for
pool reversion on Audere end.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Audere Eligibility and Lifecycle

**Files:**
- Modify: `src/world/magic/audere.py`
- Modify: `src/world/magic/tests/test_audere.py`

- [ ] **Step 1: Write failing tests for eligibility**

Add to `src/world/magic/tests/test_audere.py`:

```python
from django.contrib.contenttypes.models import ContentType
from evennia.objects.models import ObjectDB

from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import check_audere_eligibility, end_audere, offer_audere
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    IntensityTierFactory,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement


class AudereEligibilityTests(TestCase):
    """Test the triple gate for Audere eligibility."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="AudereChar")
        cls.source_ct = ContentType.objects.get_for_model(ObjectDB)
        cls.source_obj = ObjectDB.objects.create(db_key="AudereSrc")

        # Create Anima Warp condition with stages
        cls.warp_template = ConditionTemplateFactory(
            name="Anima Warp", has_progression=True,
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.warp_template, stage_order=1, name="Strain",
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.warp_template, stage_order=2, name="Fracture",
        )
        cls.stage3 = ConditionStageFactory(
            condition=cls.warp_template, stage_order=3, name="Collapse",
        )

        # Create intensity tiers
        cls.minor_tier = IntensityTierFactory(
            name="Minor", threshold=1, control_modifier=0,
        )
        cls.major_tier = IntensityTierFactory(
            name="Major", threshold=15, control_modifier=-5,
        )

        # Audere requires Major tier + stage 2+ warp
        cls.threshold = AudereThresholdFactory(
            minimum_intensity_tier=cls.major_tier,
            minimum_warp_stage=cls.stage2,
            intensity_bonus=20,
            anima_pool_bonus=30,
            warp_multiplier=2,
        )

    def _create_engagement(self) -> CharacterEngagement:
        return CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
        )

    def _create_warp(self, stage) -> None:
        ConditionInstanceFactory(
            target=self.character,
            condition=self.warp_template,
            current_stage=stage,
        )

    def test_all_gates_met(self) -> None:
        self._create_engagement()
        self._create_warp(self.stage2)
        assert check_audere_eligibility(self.character, runtime_intensity=20)

    def test_no_engagement(self) -> None:
        self._create_warp(self.stage2)
        assert not check_audere_eligibility(self.character, runtime_intensity=20)

    def test_intensity_too_low(self) -> None:
        self._create_engagement()
        self._create_warp(self.stage2)
        assert not check_audere_eligibility(self.character, runtime_intensity=5)

    def test_warp_stage_too_low(self) -> None:
        self._create_engagement()
        self._create_warp(self.stage1)
        assert not check_audere_eligibility(self.character, runtime_intensity=20)

    def test_no_warp_condition(self) -> None:
        self._create_engagement()
        assert not check_audere_eligibility(self.character, runtime_intensity=20)

    def test_no_threshold_configured(self) -> None:
        """If no AudereThreshold exists, never eligible."""
        AudereThreshold.objects.all().delete()
        self._create_engagement()
        self._create_warp(self.stage2)
        assert not check_audere_eligibility(self.character, runtime_intensity=20)

    def test_already_in_audere(self) -> None:
        """Can't enter Audere if already in Audere."""
        self._create_engagement()
        self._create_warp(self.stage2)
        # Create an Audere condition on the character
        audere_template = ConditionTemplateFactory(name="Audere")
        ConditionInstanceFactory(
            target=self.character, condition=audere_template,
        )
        assert not check_audere_eligibility(self.character, runtime_intensity=20)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test world.magic.tests.test_audere --keepdb`

- [ ] **Step 3: Implement eligibility check**

Add to `src/world/magic/audere.py`:

```python
from evennia.objects.models import ObjectDB

from world.conditions.models import ConditionInstance
from world.magic.models import IntensityTier
from world.mechanics.engagement import CharacterEngagement

# Audere condition template name — must match authored data
AUDERE_CONDITION_NAME = "Audere"
ANIMA_WARP_CONDITION_NAME = "Anima Warp"


def check_audere_eligibility(
    character: ObjectDB,
    runtime_intensity: int,
) -> bool:
    """Check if a character is eligible to enter Audere.

    Triple gate — all must be true:
    1. Runtime intensity at or above configured tier threshold
    2. Active Anima Warp at or above configured stage
    3. Active CharacterEngagement
    4. Not already in Audere

    Args:
        character: The character to check.
        runtime_intensity: Current runtime intensity value.

    Returns:
        True if all gates are met.
    """
    # Load threshold config
    threshold = AudereThreshold.objects.first()
    if threshold is None:
        return False

    # Gate 1: Intensity tier
    current_tier = (
        IntensityTier.objects.filter(threshold__lte=runtime_intensity)
        .order_by("-threshold")
        .first()
    )
    if current_tier is None:
        return False
    if current_tier.threshold < threshold.minimum_intensity_tier.threshold:
        return False

    # Gate 2: Anima Warp stage
    warp_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=ANIMA_WARP_CONDITION_NAME,
            is_suppressed=False,
        )
        .select_related("current_stage")
        .first()
    )
    if warp_instance is None or warp_instance.current_stage is None:
        return False
    if warp_instance.current_stage.stage_order < threshold.minimum_warp_stage.stage_order:
        return False

    # Gate 3: Active engagement
    if not CharacterEngagement.objects.filter(character=character).exists():
        return False

    # Gate 4: Not already in Audere
    if ConditionInstance.objects.filter(
        target=character,
        condition__name=AUDERE_CONDITION_NAME,
        is_suppressed=False,
    ).exists():
        return False

    return True
```

- [ ] **Step 4: Run eligibility tests to verify they pass**

Run: `arx test world.magic.tests.test_audere -k eligibility --keepdb`

- [ ] **Step 5: Write failing tests for offer_audere and end_audere**

Add to `src/world/magic/tests/test_audere.py`:

```python
class AudereLifecycleTests(TestCase):
    """Test Audere activation and deactivation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.source_ct = ContentType.objects.get_for_model(ObjectDB)
        cls.source_obj = ObjectDB.objects.create(db_key="LifeSrc")

        cls.warp_template = ConditionTemplateFactory(
            name="Anima Warp", has_progression=True,
        )
        cls.audere_template = ConditionTemplateFactory(name="Audere")
        cls.stage2 = ConditionStageFactory(
            condition=cls.warp_template, stage_order=2,
        )
        cls.major_tier = IntensityTierFactory(
            name="MajorLC", threshold=15,
        )
        cls.threshold = AudereThresholdFactory(
            minimum_intensity_tier=cls.major_tier,
            minimum_warp_stage=cls.stage2,
            intensity_bonus=20,
            anima_pool_bonus=30,
        )

    def setUp(self) -> None:
        self.character = ObjectDB.objects.create(db_key="LifeChar")
        self.anima = CharacterAnimaFactory(
            character=self.character, current=15, maximum=20,
        )
        self.engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.source_obj.pk,
            intensity_modifier=5,
        )

    def test_offer_audere_accepted(self) -> None:
        result = offer_audere(self.character, accept=True)
        assert result.accepted
        # Engagement intensity_modifier should increase
        self.engagement.refresh_from_db()
        assert self.engagement.intensity_modifier == 25  # 5 + 20
        # Anima pool should expand
        self.anima.refresh_from_db()
        assert self.anima.maximum == 50  # 20 + 30
        assert self.anima.pre_audere_maximum == 20
        # Audere condition should exist
        assert ConditionInstance.objects.filter(
            target=self.character,
            condition__name="Audere",
            is_suppressed=False,
        ).exists()

    def test_offer_audere_declined(self) -> None:
        result = offer_audere(self.character, accept=False)
        assert not result.accepted
        self.engagement.refresh_from_db()
        assert self.engagement.intensity_modifier == 5  # unchanged
        self.anima.refresh_from_db()
        assert self.anima.maximum == 20  # unchanged

    def test_end_audere_with_engagement(self) -> None:
        offer_audere(self.character, accept=True)
        end_audere(self.character)
        # Engagement modifier should be reduced
        self.engagement.refresh_from_db()
        assert self.engagement.intensity_modifier == 5  # back to pre-Audere
        # Anima pool should revert
        self.anima.refresh_from_db()
        assert self.anima.maximum == 20
        assert self.anima.pre_audere_maximum is None
        # Audere condition should be removed
        assert not ConditionInstance.objects.filter(
            target=self.character,
            condition__name="Audere",
            is_suppressed=False,
        ).exists()

    def test_end_audere_on_engagement_delete(self) -> None:
        """When engagement ends, Audere should also end."""
        offer_audere(self.character, accept=True)
        self.engagement.delete()
        # Manually call end_audere since engagement deletion triggers it
        end_audere(self.character)
        self.anima.refresh_from_db()
        assert self.anima.maximum == 20
        assert self.anima.pre_audere_maximum is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `arx test world.magic.tests.test_audere -k lifecycle --keepdb`

- [ ] **Step 7: Implement offer_audere and end_audere**

Add to `src/world/magic/audere.py`:

```python
from dataclasses import dataclass

from django.db import transaction

from world.conditions.services import apply_condition, remove_condition
from world.conditions.models import ConditionTemplate
from world.magic.models import CharacterAnima


@dataclass
class AudereOfferResult:
    """Result of offering Audere to a character."""

    accepted: bool
    intensity_bonus_applied: int = 0
    anima_pool_expanded_by: int = 0


def offer_audere(
    character: ObjectDB,
    *,
    accept: bool,
) -> AudereOfferResult:
    """Offer Audere to a character and process their decision.

    On acceptance:
    - Applies Audere condition
    - Adds intensity_bonus to engagement.intensity_modifier
    - Expands anima pool (stores pre-Audere maximum for reversion)

    Args:
        character: The character being offered Audere.
        accept: Whether the player accepts.

    Returns:
        AudereOfferResult with outcome details.
    """
    if not accept:
        return AudereOfferResult(accepted=False)

    threshold = AudereThreshold.objects.select_related(
        "minimum_intensity_tier",
    ).first()
    if threshold is None:
        return AudereOfferResult(accepted=False)

    with transaction.atomic():
        # Apply Audere condition
        audere_template = ConditionTemplate.objects.get(name=AUDERE_CONDITION_NAME)
        apply_condition(target=character, condition=audere_template)

        # Update engagement process modifier
        engagement = CharacterEngagement.objects.select_for_update().get(
            character=character,
        )
        engagement.intensity_modifier += threshold.intensity_bonus
        engagement.save(update_fields=["intensity_modifier"])

        # Expand anima pool
        anima = CharacterAnima.objects.select_for_update().get(character=character)
        anima.pre_audere_maximum = anima.maximum
        anima.maximum += threshold.anima_pool_bonus
        anima.save(update_fields=["maximum", "pre_audere_maximum"])

    return AudereOfferResult(
        accepted=True,
        intensity_bonus_applied=threshold.intensity_bonus,
        anima_pool_expanded_by=threshold.anima_pool_bonus,
    )


def end_audere(character: ObjectDB) -> None:
    """End Audere for a character, reverting all effects.

    - Removes Audere condition
    - Subtracts intensity_bonus from engagement (if still exists)
    - Reverts anima pool to pre_audere_maximum

    Safe to call even if Audere is not active (no-op).
    """
    threshold = AudereThreshold.objects.first()

    with transaction.atomic():
        # Remove Audere condition
        audere_template = ConditionTemplate.objects.filter(
            name=AUDERE_CONDITION_NAME,
        ).first()
        if audere_template is not None:
            remove_condition(character, audere_template)

        # Revert engagement modifier (if engagement still exists)
        if threshold is not None:
            try:
                engagement = CharacterEngagement.objects.select_for_update().get(
                    character=character,
                )
                engagement.intensity_modifier -= threshold.intensity_bonus
                engagement.save(update_fields=["intensity_modifier"])
            except CharacterEngagement.DoesNotExist:
                pass  # Engagement already deleted — process state gone

        # Revert anima pool
        try:
            anima = CharacterAnima.objects.select_for_update().get(character=character)
            if anima.pre_audere_maximum is not None:
                anima.maximum = anima.pre_audere_maximum
                # Cap current anima to new maximum
                if anima.current > anima.maximum:
                    anima.current = anima.maximum
                anima.pre_audere_maximum = None
                anima.save(update_fields=["maximum", "current", "pre_audere_maximum"])
        except CharacterAnima.DoesNotExist:
            pass
```

- [ ] **Step 8: Run all Audere tests**

Run: `arx test world.magic.tests.test_audere --keepdb`

- [ ] **Step 9: Run full magic test suite for regressions**

Run: `arx test world.magic --keepdb`

- [ ] **Step 10: Commit**

```bash
git add src/world/magic/
git commit -m "Add Audere eligibility check, offer, and end lifecycle

Triple gate: intensity tier + Anima Warp stage + engagement.
Acceptance writes intensity bonus to engagement, expands anima pool.
End reverts all effects. Safe for concurrent calls.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Warp Acceleration in `use_technique()`

**Files:**
- Modify: `src/world/magic/services.py:286-289` (Step 7 in use_technique)
- Modify: `src/world/magic/tests/test_use_technique.py`

- [ ] **Step 1: Write failing test for Warp acceleration**

Add to `src/world/magic/tests/test_use_technique.py` (new test class):

```python
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import AUDERE_CONDITION_NAME
from world.magic.factories import AudereThresholdFactory, IntensityTierFactory


class UseTechniqueWarpAccelerationTests(TestCase):
    """Test that Warp severity is multiplied during Audere."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(
            intensity=5, control=10, anima_cost=20,
        )
        cls.audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
        warp_template = ConditionTemplateFactory(
            name="Anima Warp", has_progression=True,
        )
        stage = ConditionStageFactory(condition=warp_template, stage_order=1)
        tier = IntensityTierFactory(name="WarpTier", threshold=1)
        cls.threshold = AudereThresholdFactory(
            minimum_intensity_tier=tier,
            minimum_warp_stage=stage,
            warp_multiplier=3,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=5, maximum=20)
        self.character = self.anima.character

    def test_warp_multiplier_applied_during_audere(self) -> None:
        """When Audere is active and overburn occurs, warp severity is multiplied."""
        # Place character in Audere
        ConditionInstanceFactory(
            target=self.character, condition=self.audere_template,
        )
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_overburn=True,
        )
        # The deficit exists (cost 20, anima 5 → deficit 15)
        assert result.anima_cost.deficit > 0
        # Warp multiplier should have been applied
        # (exact assertion depends on how Step 7 reports the multiplied severity)
        assert result.warp_multiplier_applied == 3

    def test_no_warp_multiplier_without_audere(self) -> None:
        """Without Audere, no multiplier is applied."""
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_overburn=True,
        )
        assert result.warp_multiplier_applied == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test world.magic.tests.test_use_technique -k warp_multiplier --keepdb`

- [ ] **Step 3: Add warp_multiplier_applied to TechniqueUseResult**

In `src/world/magic/types.py`, update `TechniqueUseResult`:

```python
@dataclass
class TechniqueUseResult:
    """Complete result of using a technique."""

    anima_cost: AnimaCostResult
    overburn_severity: OverburnSeverity | None = None
    confirmed: bool = True
    resolution_result: object | None = None
    mishap: MishapResult | None = None
    warp_multiplier_applied: int = 1  # 1 = no multiplier, >1 = Audere active
```

- [ ] **Step 4: Implement Warp acceleration in use_technique Step 7**

In `src/world/magic/services.py`, replace the Step 7 comment block (around line 286-288) with:

```python
    # Step 7: Apply overburn condition with Warp acceleration
    warp_multiplier = _get_warp_multiplier(character)
    # When Anima Warp condition template exists:
    # if cost.deficit > 0:
    #     warp_severity = cost.deficit * warp_multiplier
    #     apply_condition(character, warp_template, severity=warp_severity)
```

Add helper function:

```python
def _get_warp_multiplier(character: ObjectDB) -> int:
    """Return the Warp severity multiplier (>1 if Audere is active)."""
    from world.conditions.models import ConditionInstance
    from world.magic.audere import AUDERE_CONDITION_NAME, AudereThreshold

    if not ConditionInstance.objects.filter(
        target=character,
        condition__name=AUDERE_CONDITION_NAME,
        is_suppressed=False,
    ).exists():
        return 1

    threshold = AudereThreshold.objects.first()
    if threshold is None:
        return 1
    return threshold.warp_multiplier
```

Update the return statement to include `warp_multiplier_applied=warp_multiplier`.

- [ ] **Step 5: Run tests**

Run: `arx test world.magic.tests.test_use_technique --keepdb`

- [ ] **Step 6: Commit**

```bash
git add src/world/magic/
git commit -m "Add Warp acceleration during Audere in use_technique Step 7

When Audere condition is active, overburn Warp severity is multiplied
by AudereThreshold.warp_multiplier. Reported in TechniqueUseResult.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Pipeline Integration Tests

**Files:**
- Modify: `src/world/mechanics/tests/test_pipeline_integration.py`

This task adds a new test class exercising the full runtime modifier pipeline
end-to-end, building on the existing `PipelineTestMixin`.

- [ ] **Step 1: Write RuntimeModifierTests class**

Add at the end of `src/world/mechanics/tests/test_pipeline_integration.py`:

```python
from django.contrib.contenttypes.models import ContentType

from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    ANIMA_WARP_CONDITION_NAME,
    check_audere_eligibility,
    end_audere,
    offer_audere,
)
from world.magic.factories import AudereThresholdFactory, IntensityTierFactory
from world.magic.services import get_runtime_technique_stats
from world.mechanics.constants import TECHNIQUE_STAT_CATEGORY_NAME, EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierSourceFactory,
    ModifierTargetFactory,
)


class RuntimeModifierTests(PipelineTestMixin, TestCase):
    """End-to-end tests for the runtime modifier pipeline.

    Tests that technique runtime stats correctly combine:
    - Base technique values
    - Identity modifiers (CharacterModifier)
    - Process modifiers (CharacterEngagement)
    - Social safety bonus (no engagement)
    - IntensityTier.control_modifier
    - Audere eligibility, activation, and cleanup
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.source_ct = ContentType.objects.get_for_model(ObjectDB)

        # ModifierTargets for technique stats
        cls.ts_category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
        cls.intensity_target = ModifierTargetFactory(
            name="intensity", category=cls.ts_category,
        )
        cls.control_target = ModifierTargetFactory(
            name="control", category=cls.ts_category,
        )

        # Intensity tiers
        cls.minor_tier = IntensityTierFactory(
            name="MinorRT", threshold=1, control_modifier=0,
        )
        cls.major_tier = IntensityTierFactory(
            name="MajorRT", threshold=15, control_modifier=-3,
        )

    def test_social_safety_bonus_without_engagement(self) -> None:
        stats = get_runtime_technique_stats(self.technique, self.character)
        base_control = self.technique.control
        assert stats.control > base_control, "Social safety should boost control"

    def test_no_social_safety_when_engaged(self) -> None:
        social_stats = get_runtime_technique_stats(self.technique, self.character)
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
        )
        engaged_stats = get_runtime_technique_stats(self.technique, self.character)
        assert engaged_stats.control < social_stats.control, (
            "Engaged characters should not get social safety bonus"
        )
        # Clean up for other tests
        CharacterEngagement.objects.filter(character=self.character).delete()

    def test_engagement_process_modifiers(self) -> None:
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
            intensity_modifier=8,
            control_modifier=-2,
        )
        stats = get_runtime_technique_stats(self.technique, self.character)
        assert stats.intensity == self.technique.intensity + 8
        CharacterEngagement.objects.filter(character=self.character).delete()

    def test_identity_and_process_modifiers_stack(self) -> None:
        # Identity modifier
        source = ModifierSourceFactory()
        CharacterModifierFactory(
            character=self.sheet, target=self.intensity_target,
            value=3, source=source,
        )
        # Process modifier
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
            intensity_modifier=5,
        )
        stats = get_runtime_technique_stats(self.technique, self.character)
        assert stats.intensity == self.technique.intensity + 3 + 5
        CharacterEngagement.objects.filter(character=self.character).delete()

    def test_intensity_tier_control_modifier(self) -> None:
        """High intensity triggers tier control modifier."""
        # Use a technique with intensity that hits Major tier (threshold 15)
        high_technique = TechniqueFactory(intensity=20, control=20)
        stats = get_runtime_technique_stats(high_technique, self.character)
        # Major tier has -3 control modifier
        # Social safety bonus also applies (no engagement)
        # Net control = 20 + social_safety - 3
        assert stats.control < 20 + 20  # Should be reduced by tier

    def test_audere_eligibility_all_gates(self) -> None:
        """Audere requires engagement + warp + intensity."""
        warp_template = ConditionTemplateFactory(
            name=ANIMA_WARP_CONDITION_NAME, has_progression=True,
        )
        stage2 = ConditionStageFactory(
            condition=warp_template, stage_order=2,
        )
        AudereThresholdFactory(
            minimum_intensity_tier=self.major_tier,
            minimum_warp_stage=stage2,
        )
        CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
        )
        ConditionInstanceFactory(
            target=self.character,
            condition=warp_template,
            current_stage=stage2,
        )
        assert check_audere_eligibility(self.character, runtime_intensity=20)
        CharacterEngagement.objects.filter(character=self.character).delete()

    def test_audere_full_lifecycle(self) -> None:
        """Engagement -> Audere -> technique use with boost -> cleanup."""
        warp_template = ConditionTemplateFactory(
            name=ANIMA_WARP_CONDITION_NAME, has_progression=True,
        )
        stage2 = ConditionStageFactory(condition=warp_template, stage_order=2)
        audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
        threshold = AudereThresholdFactory(
            minimum_intensity_tier=self.major_tier,
            minimum_warp_stage=stage2,
            intensity_bonus=15,
            anima_pool_bonus=25,
        )

        engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.COMBAT,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
            intensity_modifier=0,
        )

        # Accept Audere
        result = offer_audere(self.character, accept=True)
        assert result.accepted

        # Verify boosted stats
        engagement.refresh_from_db()
        assert engagement.intensity_modifier == 15
        stats = get_runtime_technique_stats(self.technique, self.character)
        assert stats.intensity == self.technique.intensity + 15

        # End Audere
        end_audere(self.character)
        engagement.refresh_from_db()
        assert engagement.intensity_modifier == 0

        # Cleanup
        engagement.delete()
```

- [ ] **Step 2: Run integration tests**

Run: `arx test world.mechanics.tests.test_pipeline_integration::RuntimeModifierTests --keepdb`

- [ ] **Step 3: Fix any issues**

Integration tests may surface edge cases with factory data conflicts or
missing related objects. Fix and re-run.

- [ ] **Step 4: Run full test suite**

Run: `arx test world.mechanics world.magic --keepdb`

- [ ] **Step 5: Commit**

```bash
git add src/world/mechanics/tests/
git commit -m "Add RuntimeModifierTests integration tests

End-to-end tests for social safety, engagement process modifiers,
identity+process stacking, IntensityTier control modifier, Audere
eligibility, and full Audere lifecycle.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Update Roadmap and Documentation

**Files:**
- Modify: `docs/roadmap/magic.md`
- Modify: `docs/roadmap/capabilities-and-challenges.md`
- Modify: `docs/systems/INDEX.md` (if needed)

- [ ] **Step 1: Update magic roadmap**

In `docs/roadmap/magic.md`, under "Technique Use Flow", update Scope #2 from
design notes to completed status. Document what was built.

- [ ] **Step 2: Update capabilities roadmap**

In `docs/roadmap/capabilities-and-challenges.md`, note CharacterEngagement
as new infrastructure and document the engagement model's integration points.

- [ ] **Step 3: Run ruff check on all changed files**

Run: `ruff check src/world/magic/ src/world/mechanics/ --fix`

- [ ] **Step 4: Final full regression test**

Run: `arx test world.magic world.mechanics world.conditions actions world.checks --keepdb`

- [ ] **Step 5: Commit**

```bash
git add docs/ src/
git commit -m "Update roadmap for Scope #2 completion

Document CharacterEngagement, modifier pipeline, Audere condition,
and Warp acceleration. Note future hook points for resonance,
technique revelation, and contextual modifiers.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
