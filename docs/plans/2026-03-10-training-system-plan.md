# Training System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a persistent training allocation system with weekly cron processing that calculates development points from a formula combining self-study base, mentor skill ratio, teaching skill, and relationship tier, plus a rust system for unused skills.

**Architecture:** New `TrainingAllocation` model in the `skills` app. Service functions in a new `src/world/skills/services.py` for CRUD operations and weekly cron processing. A `get_relationship_tier()` stub in relationships. Integration with existing `award_development_points()` from progression and `ActionPointPool` from action_points.

**Tech Stack:** Django models (PositiveIntegerField, FK constraints, CheckConstraint), `@transaction.atomic` service functions, FactoryBoy factories, Django TestCase with `setUpTestData`.

**Design doc:** `docs/plans/2026-03-10-training-system-design.md`

---

### Task 1: TrainingAllocation Model

**Files:**
- Modify: `src/world/skills/models.py` (add TrainingAllocation class at end)
- Create: `src/world/skills/tests/test_training.py` (new test file)

**Context:** The `skills` app already has `Skill`, `Specialization`, `CharacterSkillValue`, `CharacterSpecializationValue`. We're adding `TrainingAllocation` — a persistent record of a character's weekly training plan entry. Each row represents one skill+mentor+AP allocation. A character can have multiple rows (training multiple skills). The model stores:
- `character` (FK → ObjectDB) — the character training
- `skill` (FK → Skill, nullable) — set when training a parent skill
- `specialization` (FK → Specialization, nullable) — set when training a specialization
- `mentor` (FK → Guise, nullable) — null means self-study
- `ap_amount` (PositiveIntegerField) — AP allocated per week

Constraints:
- Either `skill` or `specialization` must be set, not both (CheckConstraint)
- One allocation per skill per character, one per specialization per character (unique_together)
- `ap_amount` minimum 1

**Step 1: Write the model test**

In `src/world/skills/tests/test_training.py`:

```python
"""Tests for the training allocation system."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import GuiseFactory
from world.skills.factories import CharacterSkillValueFactory, SkillFactory, SpecializationFactory
from world.skills.models import TrainingAllocation


class TrainingAllocationModelTests(TestCase):
    """Tests for TrainingAllocation model."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()
        cls.specialization = SpecializationFactory(parent_skill=cls.skill)
        cls.mentor = GuiseFactory()

    def test_create_skill_allocation(self) -> None:
        """Can create an allocation for a skill with a mentor."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            mentor=self.mentor,
            ap_amount=20,
        )
        self.assertEqual(alloc.character, self.character)
        self.assertEqual(alloc.skill, self.skill)
        self.assertIsNone(alloc.specialization)
        self.assertEqual(alloc.mentor, self.mentor)
        self.assertEqual(alloc.ap_amount, 20)

    def test_create_specialization_allocation(self) -> None:
        """Can create an allocation for a specialization."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            specialization=self.specialization,
            ap_amount=10,
        )
        self.assertIsNone(alloc.skill)
        self.assertEqual(alloc.specialization, self.specialization)
        self.assertIsNone(alloc.mentor)

    def test_create_self_study(self) -> None:
        """Null mentor means self-study."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            ap_amount=5,
        )
        self.assertIsNone(alloc.mentor)

    def test_unique_skill_per_character(self) -> None:
        """Cannot create two allocations for same skill+character."""
        TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            ap_amount=10,
        )
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                skill=self.skill,
                ap_amount=5,
            )

    def test_unique_specialization_per_character(self) -> None:
        """Cannot create two allocations for same specialization+character."""
        TrainingAllocation.objects.create(
            character=self.character,
            specialization=self.specialization,
            ap_amount=10,
        )
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                specialization=self.specialization,
                ap_amount=5,
            )

    def test_str_skill(self) -> None:
        """String representation includes character and skill name."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            ap_amount=10,
        )
        result = str(alloc)
        self.assertIn(self.character.db_key, result)
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.skills.tests.test_training
```

Expected: FAIL — `TrainingAllocation` does not exist yet.

**Step 3: Write the model**

Add to end of `src/world/skills/models.py`:

```python
class TrainingAllocation(models.Model):
    """
    Persistent weekly training plan entry.

    Each row represents one skill+mentor+AP allocation for a character.
    Characters can have multiple allocations (training multiple skills).
    Persists week to week until the player modifies or removes it.
    At weekly cron, each allocation is processed to award development points.
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="training_allocations",
        help_text="The character training",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="training_allocations",
        help_text="The skill being trained (null if training a specialization)",
    )
    specialization = models.ForeignKey(
        Specialization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="training_allocations",
        help_text="The specialization being trained (null if training a parent skill)",
    )
    mentor = models.ForeignKey(
        "character_sheets.Guise",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mentored_allocations",
        help_text="The mentor guise (null = self-study)",
    )
    ap_amount = models.PositiveIntegerField(
        help_text="Action points allocated per week (minimum 1)",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(skill__isnull=False, specialization__isnull=True)
                    | models.Q(skill__isnull=True, specialization__isnull=False)
                ),
                name="training_skill_xor_specialization",
            ),
        ]
        unique_together = [
            ["character", "skill"],
            ["character", "specialization"],
        ]
        indexes = [
            models.Index(fields=["character"]),
        ]

    def __str__(self) -> str:
        target = self.skill.trait.name if self.skill else self.specialization.name
        return f"{self.character.db_key}: {target} ({self.ap_amount} AP)"
```

**Step 4: Generate and apply migration**

```bash
arx manage makemigrations skills && arx manage migrate
```

**Step 5: Run tests to verify they pass**

```bash
echo "yes" | arx test world.skills.tests.test_training
```

Expected: PASS

**Step 6: Lint and commit**

```bash
ruff check src/world/skills/models.py src/world/skills/tests/test_training.py
ruff format src/world/skills/models.py src/world/skills/tests/test_training.py
```

---

### Task 2: TrainingAllocation Factory and Admin

**Files:**
- Modify: `src/world/skills/factories.py` (add TrainingAllocationFactory)
- Modify: `src/world/skills/admin.py` (add TrainingAllocationAdmin)

**Context:** Every model needs a factory for tests and admin registration. Follow existing patterns from the skills app.

**Step 1: Add factory**

Add to `src/world/skills/factories.py`:

```python
from world.skills.models import TrainingAllocation

class TrainingAllocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TrainingAllocation

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    skill = factory.SubFactory(SkillFactory)
    specialization = None
    mentor = None
    ap_amount = 10
```

**Step 2: Add admin**

Add to `src/world/skills/admin.py`:

```python
from world.skills.models import TrainingAllocation

@admin.register(TrainingAllocation)
class TrainingAllocationAdmin(admin.ModelAdmin):
    list_display = ["character", "skill", "specialization", "mentor", "ap_amount"]
    list_filter = ["skill", "specialization"]
    raw_id_fields = ["character", "mentor"]
```

**Step 3: Run tests**

```bash
echo "yes" | arx test world.skills
```

**Step 4: Lint and commit**

```bash
ruff check src/world/skills/factories.py src/world/skills/admin.py
ruff format src/world/skills/factories.py src/world/skills/admin.py
```

---

### Task 3: Relationship Tier Stub

**Files:**
- Create: `src/world/relationships/helpers.py`
- Create: `src/world/relationships/tests/test_helpers.py`

**Context:** The training formula uses `(relationship_tier + 1)` as a multiplier. The actual tier calculation depends on relationship points and tiers that aren't fully defined yet. We create a stub function `get_relationship_tier()` that always returns 0, with a clear TODO. The function signature should accept two characters (or a CharacterRelationship) and return an int.

**Step 1: Write the test**

In `src/world/relationships/tests/test_helpers.py`:

```python
"""Tests for relationship helper functions."""

from django.test import TestCase
from evennia_extensions.factories import CharacterFactory

from world.relationships.helpers import get_relationship_tier


class GetRelationshipTierTests(TestCase):
    """Tests for get_relationship_tier stub."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.char_a = CharacterFactory()
        cls.char_b = CharacterFactory()

    def test_returns_zero_stub(self) -> None:
        """Stub always returns 0 until relationship tiers are defined."""
        tier = get_relationship_tier(self.char_a, self.char_b)
        self.assertEqual(tier, 0)

    def test_returns_int(self) -> None:
        """Return type is int."""
        tier = get_relationship_tier(self.char_a, self.char_b)
        self.assertIsInstance(tier, int)
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.relationships.tests.test_helpers
```

**Step 3: Write the stub**

In `src/world/relationships/helpers.py`:

```python
"""Helper functions for the relationships system."""

from evennia.objects.models import ObjectDB


def get_relationship_tier(character_a: ObjectDB, character_b: ObjectDB) -> int:
    """Get the relationship tier between two characters.

    TODO: Implement actual tier calculation from RelationshipTrackProgress
    point values once tier breakpoints are defined. Currently returns 0
    (no relationship bonus). The training system uses this as:
    mentor_bonus *= (relationship_tier + 1)

    Args:
        character_a: First character.
        character_b: Second character.

    Returns:
        Relationship tier as an integer (0 = no/new relationship).
    """
    return 0
```

**Step 4: Run tests to verify they pass**

```bash
echo "yes" | arx test world.relationships.tests.test_helpers
```

**Step 5: Lint and commit**

---

### Task 4: Training Calculation Helper — `calculate_training_development`

**Files:**
- Create: `src/world/skills/services.py`
- Modify: `src/world/skills/tests/test_training.py` (add calculation tests)

**Context:** This is the core formula from the design doc. The function takes a `TrainingAllocation` and returns the development points earned. It needs to:
1. Look up the student's current skill/specialization value
2. If mentor exists, look up mentor's skill values and teaching skill
3. Look up the student's path level (from `CharacterClassLevel`, using highest level)
4. Look up relationship tier (from stub)
5. Calculate `base_gain = 5 × AP × path_level`
6. Calculate `mentor_bonus = (AP + teaching) × (mentor_total / student_total) × (relationship_tier + 1)`
7. Return `base_gain + mentor_bonus` as an integer

**Important implementation details:**
- `CharacterSkillValue.value` stores values as 10, 20, 30 etc. (multiply by 10 internally). Use raw values for the ratio.
- For specialization training, student total = specialization value + parent skill value. Mentor total = mentor's specialization + mentor's parent + teaching.
- For skill training, student total = skill value. Mentor total = mentor's skill value + teaching.
- Path level comes from `character.character_class_levels.all()` — take the highest `level` field, default to 1 if none.
- Teaching skill: look up the mentor character's `CharacterSkillValue` for a `Skill` named "Teaching". If not found, teaching = 0.

**Step 1: Write the calculation tests**

Add to `src/world/skills/tests/test_training.py`:

```python
from world.skills.services import calculate_training_development


class CalculateTrainingDevelopmentTests(TestCase):
    """Tests for calculate_training_development formula."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Student guise + character
        cls.student_guise = GuiseFactory()
        cls.student = cls.student_guise.character

        # Skill setup
        cls.skill = SkillFactory()

        # Student has skill value 40 (stored as 40 in the DB)
        cls.student_skill = CharacterSkillValueFactory(
            character=cls.student,
            skill=cls.skill,
            value=40,
        )

        # Mentor guise + character
        cls.mentor_guise = GuiseFactory()
        cls.mentor = cls.mentor_guise.character

        # Mentor has skill value 100
        CharacterSkillValueFactory(
            character=cls.mentor,
            skill=cls.skill,
            value=100,
        )

        # Teaching skill for mentor
        cls.teaching_skill = SkillFactory()
        cls.teaching_skill.trait.name = "Teaching"
        cls.teaching_skill.trait.save()
        CharacterSkillValueFactory(
            character=cls.mentor,
            skill=cls.teaching_skill,
            value=20,
        )

        # Path level for student (need CharacterClassLevel)
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=cls.student, level=5)

    def test_self_study_base_gain(self) -> None:
        """Self-study: base_gain = 5 * AP * path_level."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        result = calculate_training_development(alloc)
        # 5 * 20 * 5 = 500
        self.assertEqual(result, 500)

    def test_with_mentor(self) -> None:
        """With mentor: base_gain + mentor_bonus."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            mentor=self.mentor_guise,
            ap_amount=20,
        )
        result = calculate_training_development(alloc)
        # base = 5 * 20 * 5 = 500
        # mentor_total = 100 (skill) + 20 (teaching) = 120
        # student_total = 40
        # ratio = 120 / 40 = 3.0
        # effective_AP = 20 + 20 = 40
        # relationship_tier = 0 (stub), so (0 + 1) = 1
        # mentor_bonus = 40 * 3.0 * 1 = 120
        # total = 500 + 120 = 620
        self.assertEqual(result, 620)

    def test_no_path_level_defaults_to_one(self) -> None:
        """Character with no class levels uses path_level=1."""
        student_guise = GuiseFactory()
        student = student_guise.character
        CharacterSkillValueFactory(character=student, skill=self.skill, value=20)
        alloc = TrainingAllocation.objects.create(
            character=student,
            skill=self.skill,
            ap_amount=10,
        )
        result = calculate_training_development(alloc)
        # 5 * 10 * 1 = 50
        self.assertEqual(result, 50)

    def test_returns_integer(self) -> None:
        """Result is always an integer (truncated)."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            mentor=self.mentor_guise,
            ap_amount=7,
        )
        result = calculate_training_development(alloc)
        self.assertIsInstance(result, int)
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.skills.tests.test_training.CalculateTrainingDevelopmentTests
```

**Step 3: Write the service function**

Create `src/world/skills/services.py`:

```python
"""Service functions for the skill training system.

Provides functions for managing training allocations and processing
weekly training development point gains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.relationships.helpers import get_relationship_tier
from world.skills.models import CharacterSkillValue, Skill, TrainingAllocation

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB
    from world.character_sheets.models import Guise


def _get_path_level(character: ObjectDB) -> int:
    """Get the character's highest path level, defaulting to 1.

    Args:
        character: The character to check.

    Returns:
        Highest class level, or 1 if no class levels exist.
    """
    class_levels = character.character_class_levels.all()
    if not class_levels.exists():
        return 1
    return max(ccl.level for ccl in class_levels)


def _get_skill_value(character: ObjectDB, skill: Skill) -> int:
    """Get a character's current value for a skill, defaulting to 0.

    Args:
        character: The character to look up.
        skill: The skill to check.

    Returns:
        The skill value, or 0 if not found.
    """
    try:
        csv = CharacterSkillValue.objects.get(character=character, skill=skill)
        return csv.value
    except CharacterSkillValue.DoesNotExist:
        return 0


def _get_teaching_value(mentor_character: ObjectDB) -> int:
    """Get the mentor's Teaching skill value.

    Args:
        mentor_character: The mentor's character object.

    Returns:
        Teaching skill value, or 0 if no Teaching skill exists.
    """
    try:
        teaching_skill = Skill.objects.get(trait__name="Teaching")
        return _get_skill_value(mentor_character, teaching_skill)
    except Skill.DoesNotExist:
        return 0


def calculate_training_development(allocation: TrainingAllocation) -> int:
    """Calculate development points earned from a training allocation.

    Formula:
        base_gain = 5 * AP_spent * path_level
        If mentor:
            mentor_total = mentor_skill + teaching (+ parent if specialization)
            student_total = student_skill (+ parent if specialization)
            ratio = mentor_total / student_total
            effective_AP = AP_spent + teaching
            mentor_bonus = effective_AP * ratio * (relationship_tier + 1)
        dev_points = base_gain + mentor_bonus

    Args:
        allocation: The training allocation to calculate for.

    Returns:
        Development points earned as an integer.
    """
    character = allocation.character
    ap_spent = allocation.ap_amount
    path_level = _get_path_level(character)

    base_gain = 5 * ap_spent * path_level

    if not allocation.mentor:
        return base_gain

    mentor_character = allocation.mentor.character
    teaching_value = _get_teaching_value(mentor_character)

    if allocation.specialization:
        spec = allocation.specialization
        parent_skill = spec.parent_skill
        student_total = (
            _get_skill_value(character, parent_skill)
            + _get_spec_value(character, spec)
        )
        mentor_total = (
            _get_skill_value(mentor_character, parent_skill)
            + _get_spec_value(mentor_character, spec)
            + teaching_value
        )
    else:
        skill = allocation.skill
        student_total = _get_skill_value(character, skill)
        mentor_total = _get_skill_value(mentor_character, skill) + teaching_value

    if student_total == 0:
        student_total = 1  # Prevent division by zero

    ratio = mentor_total / student_total
    effective_ap = ap_spent + teaching_value
    relationship_tier = get_relationship_tier(character, mentor_character)
    mentor_bonus = effective_ap * ratio * (relationship_tier + 1)

    return int(base_gain + mentor_bonus)
```

Also add `_get_spec_value` helper:

```python
from world.skills.models import CharacterSpecializationValue, Specialization


def _get_spec_value(character: ObjectDB, specialization: Specialization) -> int:
    """Get a character's current value for a specialization, defaulting to 0.

    Args:
        character: The character to look up.
        specialization: The specialization to check.

    Returns:
        The specialization value, or 0 if not found.
    """
    try:
        csv = CharacterSpecializationValue.objects.get(
            character=character, specialization=specialization,
        )
        return csv.value
    except CharacterSpecializationValue.DoesNotExist:
        return 0
```

**Step 4: Run tests to verify they pass**

```bash
echo "yes" | arx test world.skills.tests.test_training.CalculateTrainingDevelopmentTests
```

**Step 5: Lint and commit**

---

### Task 5: Specialization Training Calculation Tests

**Files:**
- Modify: `src/world/skills/tests/test_training.py` (add specialization tests)

**Context:** The formula for specialization training uses parent_skill + specialization for both student and mentor totals. Also need a `SpecializationFactory` and `CharacterSpecializationValueFactory`.

**Step 1: Write specialization calculation tests**

Add to `src/world/skills/tests/test_training.py`:

```python
from world.skills.factories import CharacterSpecializationValueFactory


class CalculateSpecializationTrainingTests(TestCase):
    """Tests for specialization training development calculation."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.student_guise = GuiseFactory()
        cls.student = cls.student_guise.character

        cls.skill = SkillFactory()
        cls.spec = SpecializationFactory(parent_skill=cls.skill)

        # Student: parent=30, spec=10, total=40
        CharacterSkillValueFactory(character=cls.student, skill=cls.skill, value=30)
        CharacterSpecializationValueFactory(
            character=cls.student, specialization=cls.spec, value=10,
        )

        # Mentor: parent=50, spec=50, teaching=20, total=120
        cls.mentor_guise = GuiseFactory()
        cls.mentor = cls.mentor_guise.character
        CharacterSkillValueFactory(character=cls.mentor, skill=cls.skill, value=50)
        CharacterSpecializationValueFactory(
            character=cls.mentor, specialization=cls.spec, value=50,
        )
        cls.teaching_skill = SkillFactory()
        cls.teaching_skill.trait.name = "Teaching"
        cls.teaching_skill.trait.save()
        CharacterSkillValueFactory(
            character=cls.mentor, skill=cls.teaching_skill, value=20,
        )

        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=cls.student, level=5)

    def test_specialization_with_mentor(self) -> None:
        """Spec training uses parent+spec for both student and mentor."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            specialization=self.spec,
            mentor=self.mentor_guise,
            ap_amount=20,
        )
        result = calculate_training_development(alloc)
        # base = 5 * 20 * 5 = 500
        # student_total = 30 + 10 = 40
        # mentor_total = 50 + 50 + 20 = 120
        # ratio = 120 / 40 = 3.0
        # effective_AP = 20 + 20 = 40
        # relationship = (0 + 1) = 1
        # mentor_bonus = 40 * 3.0 * 1 = 120
        # total = 500 + 120 = 620
        self.assertEqual(result, 620)

    def test_specialization_self_study(self) -> None:
        """Specialization self-study only uses base gain."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            specialization=self.spec,
            ap_amount=10,
        )
        result = calculate_training_development(alloc)
        # 5 * 10 * 5 = 250
        self.assertEqual(result, 250)
```

**Step 2: Run tests**

```bash
echo "yes" | arx test world.skills.tests.test_training.CalculateSpecializationTrainingTests
```

**Step 3: Fix any issues, lint and commit**

---

### Task 6: CRUD Service Functions

**Files:**
- Modify: `src/world/skills/services.py` (add CRUD functions)
- Modify: `src/world/skills/tests/test_training.py` (add CRUD tests)

**Context:** Service functions for creating, updating, and removing training allocations. These validate that total AP across all allocations doesn't exceed the character's weekly AP regen. The `ActionPointConfig` has `weekly_regen` (default 100) which is the budget ceiling.

**Step 1: Write tests for CRUD operations**

Add to `src/world/skills/tests/test_training.py`:

```python
from world.action_points.models import ActionPointConfig
from world.skills.services import (
    create_training_allocation,
    remove_training_allocation,
    update_training_allocation,
)


class CreateTrainingAllocationTests(TestCase):
    """Tests for create_training_allocation service."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()
        cls.mentor = GuiseFactory()

    def test_creates_allocation(self) -> None:
        """Creates a valid allocation."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        self.assertEqual(alloc.character, self.character)
        self.assertEqual(alloc.skill, self.skill)
        self.assertEqual(alloc.ap_amount, 20)

    def test_with_mentor(self) -> None:
        """Creates allocation with mentor."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            mentor=self.mentor,
            ap_amount=10,
        )
        self.assertEqual(alloc.mentor, self.mentor)

    def test_rejects_exceeding_weekly_budget(self) -> None:
        """Raises ValueError if total AP would exceed weekly regen."""
        config = ActionPointConfig.get_active_config()
        create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=config.weekly_regen,
        )
        skill2 = SkillFactory()
        with self.assertRaises(ValueError):
            create_training_allocation(
                character=self.character,
                skill=skill2,
                ap_amount=1,
            )

    def test_rejects_zero_ap(self) -> None:
        """Raises ValueError for 0 AP."""
        with self.assertRaises(ValueError):
            create_training_allocation(
                character=self.character,
                skill=self.skill,
                ap_amount=0,
            )


class UpdateTrainingAllocationTests(TestCase):
    """Tests for update_training_allocation service."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()

    def test_updates_ap_amount(self) -> None:
        """Can update the AP amount."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        updated = update_training_allocation(alloc, ap_amount=30)
        self.assertEqual(updated.ap_amount, 30)

    def test_updates_mentor(self) -> None:
        """Can change mentor."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        mentor = GuiseFactory()
        updated = update_training_allocation(alloc, mentor=mentor)
        self.assertEqual(updated.mentor, mentor)

    def test_rejects_exceeding_budget_on_update(self) -> None:
        """Raises ValueError if updated total exceeds budget."""
        config = ActionPointConfig.get_active_config()
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=config.weekly_regen,
        )
        with self.assertRaises(ValueError):
            update_training_allocation(alloc, ap_amount=config.weekly_regen + 1)


class RemoveTrainingAllocationTests(TestCase):
    """Tests for remove_training_allocation service."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()

    def test_removes_allocation(self) -> None:
        """Deletes the allocation."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        remove_training_allocation(alloc)
        self.assertFalse(
            TrainingAllocation.objects.filter(pk=alloc.pk).exists()
        )
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.skills.tests.test_training.CreateTrainingAllocationTests
```

**Step 3: Write service functions**

Add to `src/world/skills/services.py`:

```python
from django.db.models import Sum

from world.action_points.models import ActionPointConfig


def _get_total_allocated_ap(character: ObjectDB, exclude_pk: int | None = None) -> int:
    """Get total AP currently allocated across all training for a character.

    Args:
        character: The character to check.
        exclude_pk: Optional allocation PK to exclude (for updates).

    Returns:
        Total AP allocated.
    """
    qs = TrainingAllocation.objects.filter(character=character)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.aggregate(total=Sum("ap_amount"))["total"] or 0


def create_training_allocation(
    character: ObjectDB,
    ap_amount: int,
    *,
    skill: Skill | None = None,
    specialization: Specialization | None = None,
    mentor: Guise | None = None,
) -> TrainingAllocation:
    """Create a new training allocation for a character.

    Args:
        character: The character training.
        ap_amount: AP to allocate per week.
        skill: The skill to train (mutually exclusive with specialization).
        specialization: The specialization to train.
        mentor: Optional mentor guise (null = self-study).

    Returns:
        The created TrainingAllocation.

    Raises:
        ValueError: If ap_amount is 0 or total would exceed weekly budget.
    """
    if ap_amount <= 0:
        msg = "AP amount must be at least 1."
        raise ValueError(msg)

    config = ActionPointConfig.get_active_config()
    current_total = _get_total_allocated_ap(character)
    if current_total + ap_amount > config.weekly_regen:
        msg = (
            f"Total AP ({current_total + ap_amount}) would exceed "
            f"weekly budget ({config.weekly_regen})."
        )
        raise ValueError(msg)

    return TrainingAllocation.objects.create(
        character=character,
        skill=skill,
        specialization=specialization,
        mentor=mentor,
        ap_amount=ap_amount,
    )


def update_training_allocation(
    allocation: TrainingAllocation,
    *,
    ap_amount: int | None = None,
    mentor: Guise | None = ...,  # type: ignore[assignment]
) -> TrainingAllocation:
    """Update an existing training allocation.

    Args:
        allocation: The allocation to update.
        ap_amount: New AP amount (if changing).
        mentor: New mentor (if changing). Pass None to remove mentor.

    Returns:
        The updated TrainingAllocation.

    Raises:
        ValueError: If updated total would exceed weekly budget.
    """
    if ap_amount is not None:
        if ap_amount <= 0:
            msg = "AP amount must be at least 1."
            raise ValueError(msg)

        config = ActionPointConfig.get_active_config()
        current_total = _get_total_allocated_ap(
            allocation.character, exclude_pk=allocation.pk,
        )
        if current_total + ap_amount > config.weekly_regen:
            msg = (
                f"Total AP ({current_total + ap_amount}) would exceed "
                f"weekly budget ({config.weekly_regen})."
            )
            raise ValueError(msg)
        allocation.ap_amount = ap_amount

    if mentor is not ...:
        allocation.mentor = mentor

    allocation.save()
    return allocation


def remove_training_allocation(allocation: TrainingAllocation) -> None:
    """Remove a training allocation.

    Args:
        allocation: The allocation to delete.
    """
    allocation.delete()
```

**Step 4: Run tests**

```bash
echo "yes" | arx test world.skills.tests.test_training
```

**Step 5: Lint and commit**

---

### Task 7: Weekly Training Processing Service

**Files:**
- Modify: `src/world/skills/services.py` (add `process_weekly_training`)
- Modify: `src/world/skills/tests/test_training.py` (add processing tests)

**Context:** The core cron function. Iterates all `TrainingAllocation` rows, calculates dev points, awards them via `award_development_points()`, and consumes AP. Must handle:
- X9 boundaries: skill 19, 29, 39, 49 — dev points wasted but skill marked active
- Overflow carries over: dev points accumulate and can level up multiple times
- AP consumption from `ActionPointPool`

**Important:** `award_development_points()` takes a `Trait` (not a `Skill`). Use `skill.trait` to get the trait. For specializations, we need to think about this — specializations don't have their own trait. Development points for specializations should go to `CharacterSpecializationValue.development_points` directly, not through `award_development_points()`. We'll need a separate helper for specialization development.

Actually, looking at the code more carefully: `DevelopmentPoints` tracks per-trait development, and `CharacterSkillValue` has its own `development_points` field. These may be separate tracking. The implementer should check how `award_development_points()` actually applies points and whether `CharacterSkillValue.development_points` is updated by it or separately. For the plan, we'll create our own `apply_training_development()` function that directly updates `CharacterSkillValue.development_points` (or `CharacterSpecializationValue.development_points`) with the level-up logic.

**Step 1: Write the processing tests**

Add to `src/world/skills/tests/test_training.py`:

```python
from world.action_points.models import ActionPointPool
from world.skills.services import process_weekly_training


class ProcessWeeklyTrainingTests(TestCase):
    """Tests for process_weekly_training cron function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.student_guise = GuiseFactory()
        cls.student = cls.student_guise.character
        cls.skill = SkillFactory()
        cls.student_skill = CharacterSkillValueFactory(
            character=cls.student,
            skill=cls.skill,
            value=10,
            development_points=0,
        )
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=cls.student, level=1)

    def test_awards_development_points(self) -> None:
        """Training awards development points to the skill."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        trained_skills = process_weekly_training()
        self.student_skill.refresh_from_db()
        # base = 5 * 10 * 1 = 50
        self.assertEqual(self.student_skill.development_points, 50)
        self.assertIn(self.student.pk, trained_skills)

    def test_levels_up_on_threshold(self) -> None:
        """Skill levels up when dev points exceed cost."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # base = 5 * 20 * 1 = 100. Cost 10->11 = 100. Level up!
        self.assertEqual(self.student_skill.value, 11)
        self.assertEqual(self.student_skill.development_points, 0)

    def test_overflow_carries_over(self) -> None:
        """Excess dev points carry into next level."""
        self.student_skill.development_points = 50
        self.student_skill.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # Had 50 + gained 100 = 150. Cost 10->11 = 100. Overflow = 50.
        self.assertEqual(self.student_skill.value, 11)
        self.assertEqual(self.student_skill.development_points, 50)

    def test_multiple_level_ups(self) -> None:
        """Can gain multiple levels in one week with enough dev points."""
        from world.classes.models import CharacterClassLevel

        ccl = CharacterClassLevel.objects.get(character=self.student)
        ccl.level = 5
        ccl.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # base = 5 * 20 * 5 = 500. Cost 10->11=100, 11->12=200. Total=300.
        # 500-300 = 200 left, cost 12->13=300. Can't. So level 12, 200 dev.
        self.assertEqual(self.student_skill.value, 12)
        self.assertEqual(self.student_skill.development_points, 200)

    def test_stops_at_x9_boundary(self) -> None:
        """Dev points are wasted at X9 boundaries (19, 29, etc.)."""
        self.student_skill.value = 19
        self.student_skill.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # At boundary, points wasted
        self.assertEqual(self.student_skill.value, 19)
        self.assertEqual(self.student_skill.development_points, 0)

    def test_consumes_ap(self) -> None:
        """AP is consumed from the character's pool."""
        pool, _ = ActionPointPool.objects.get_or_create(
            db_obj=self.student,
            defaults={"current": 100, "maximum": 200},
        )
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        pool.refresh_from_db()
        self.assertEqual(pool.current, 80)

    def test_returns_trained_skills_set(self) -> None:
        """Returns dict mapping character PKs to sets of trained skill PKs."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        result = process_weekly_training()
        self.assertIn(self.skill.pk, result[self.student.pk])
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.skills.tests.test_training.ProcessWeeklyTrainingTests
```

**Step 3: Write the processing service**

Add to `src/world/skills/services.py`:

```python
from collections import defaultdict

from django.db import transaction


def _development_cost(current_value: int) -> int:
    """Calculate development point cost to reach the next skill level.

    Cost = (current_value - 9) * 100
    So: 10->11 = 100, 11->12 = 200, 15->16 = 600, etc.

    Args:
        current_value: Current skill value.

    Returns:
        Development points needed for next level.
    """
    return (current_value - 9) * 100


def _is_at_xp_boundary(value: int) -> bool:
    """Check if a skill value is at an XP purchase boundary (X9).

    Args:
        value: Current skill value.

    Returns:
        True if at 19, 29, 39, or 49.
    """
    return value % 10 == 9 and value >= 19


def _apply_development_to_skill(
    skill_value: CharacterSkillValue,
    dev_points: int,
) -> None:
    """Apply development points to a skill, handling level-ups and overflow.

    Mutates the skill_value in place and saves.

    Args:
        skill_value: The CharacterSkillValue to update.
        dev_points: Development points to apply.
    """
    if _is_at_xp_boundary(skill_value.value):
        # At boundary — points wasted, don't accumulate
        return

    remaining = skill_value.development_points + dev_points

    while remaining > 0:
        if _is_at_xp_boundary(skill_value.value):
            # Hit boundary during level-ups — stop, waste remaining
            remaining = 0
            break

        cost = _development_cost(skill_value.value)
        if remaining >= cost:
            remaining -= cost
            skill_value.value += 1
        else:
            break

    skill_value.development_points = remaining
    skill_value.save()


def _apply_development_to_specialization(
    spec_value: CharacterSpecializationValue,
    dev_points: int,
) -> None:
    """Apply development points to a specialization, handling level-ups.

    Same logic as skills but specializations have no XP boundaries.

    Args:
        spec_value: The CharacterSpecializationValue to update.
        dev_points: Development points to apply.
    """
    remaining = spec_value.development_points + dev_points

    while remaining > 0:
        cost = _development_cost(spec_value.value)
        if remaining >= cost:
            remaining -= cost
            spec_value.value += 1
        else:
            break

    spec_value.development_points = remaining
    spec_value.save()


@transaction.atomic
def process_weekly_training() -> dict[int, set[int]]:
    """Process all training allocations for the weekly cron.

    For each allocation:
    1. Calculate development points from the training formula.
    2. Apply dev points (with level-ups and overflow).
    3. Consume AP from the character's ActionPointPool.

    Returns:
        Dict mapping character PKs to sets of trained Skill PKs
        (used by rust system to know which skills were active).
    """
    trained_skills: dict[int, set[int]] = defaultdict(set)
    allocations = TrainingAllocation.objects.select_related(
        "character",
        "skill",
        "skill__trait",
        "specialization",
        "specialization__parent_skill",
        "mentor",
        "mentor__character",
    ).all()

    for allocation in allocations:
        dev_points = calculate_training_development(allocation)
        character = allocation.character

        if allocation.skill:
            skill_value, _ = CharacterSkillValue.objects.get_or_create(
                character=character,
                skill=allocation.skill,
                defaults={"value": 10, "development_points": 0, "rust_points": 0},
            )
            _apply_development_to_skill(skill_value, dev_points)
            trained_skills[character.pk].add(allocation.skill.pk)
        elif allocation.specialization:
            spec_value, _ = CharacterSpecializationValue.objects.get_or_create(
                character=character,
                specialization=allocation.specialization,
                defaults={"value": 10, "development_points": 0},
            )
            _apply_development_to_specialization(spec_value, dev_points)
            # Training specialization prevents rust on parent skill too
            trained_skills[character.pk].add(
                allocation.specialization.parent_skill.pk
            )

        # Consume AP
        try:
            pool = ActionPointPool.objects.get(db_obj=character)
            pool.spend(allocation.ap_amount)
        except ActionPointPool.DoesNotExist:
            pass  # No pool, no AP to consume

    return trained_skills
```

**Step 4: Run tests**

```bash
echo "yes" | arx test world.skills.tests.test_training.ProcessWeeklyTrainingTests
```

**Step 5: Lint and commit**

---

### Task 8: Weekly Rust Processing Service

**Files:**
- Modify: `src/world/skills/services.py` (add `apply_weekly_rust`)
- Modify: `src/world/skills/tests/test_training.py` (add rust tests)

**Context:** After training processes, rust is applied to all skills that didn't receive development this week. Rust = `character_level + 5` per week, capped at the current level's dev cost. Rust accumulates in `CharacterSkillValue.rust_points`. When development is later applied, rust must be paid off first before forward progress.

**Step 1: Write rust tests**

Add to `src/world/skills/tests/test_training.py`:

```python
from world.skills.services import apply_weekly_rust


class ApplyWeeklyRustTests(TestCase):
    """Tests for apply_weekly_rust function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()
        cls.skill_value = CharacterSkillValueFactory(
            character=cls.character,
            skill=cls.skill,
            value=11,
            rust_points=0,
        )
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=cls.character, level=5)

    def test_adds_rust_to_unused_skill(self) -> None:
        """Unused skill gains character_level + 5 rust."""
        apply_weekly_rust(trained_skills={})
        self.skill_value.refresh_from_db()
        # level 5 + 5 = 10 rust
        self.assertEqual(self.skill_value.rust_points, 10)

    def test_no_rust_on_trained_skill(self) -> None:
        """Trained skill gets no rust."""
        trained = {self.character.pk: {self.skill.pk}}
        apply_weekly_rust(trained_skills=trained)
        self.skill_value.refresh_from_db()
        self.assertEqual(self.skill_value.rust_points, 0)

    def test_rust_caps_at_level_cost(self) -> None:
        """Rust cannot exceed current level's development cost."""
        # Skill 11: cost = (11-9)*100 = 200
        self.skill_value.rust_points = 195
        self.skill_value.save()
        apply_weekly_rust(trained_skills={})
        self.skill_value.refresh_from_db()
        # Would add 10, but cap is 200, so 200
        self.assertEqual(self.skill_value.rust_points, 200)

    def test_rust_accumulates_over_weeks(self) -> None:
        """Rust accumulates across multiple calls."""
        apply_weekly_rust(trained_skills={})
        apply_weekly_rust(trained_skills={})
        self.skill_value.refresh_from_db()
        # 10 + 10 = 20
        self.assertEqual(self.skill_value.rust_points, 20)

    def test_development_pays_off_rust_first(self) -> None:
        """When rust exists, dev points pay rust before advancing."""
        self.skill_value.rust_points = 50
        self.skill_value.save()
        # Apply 80 dev points: 50 clears rust, 30 goes to development
        _apply_development_to_skill(self.skill_value, 80)
        self.assertEqual(self.skill_value.rust_points, 0)
        self.assertEqual(self.skill_value.development_points, 30)
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.skills.tests.test_training.ApplyWeeklyRustTests
```

**Step 3: Write rust service + update development function to handle rust**

Add to `src/world/skills/services.py`:

```python
def apply_weekly_rust(trained_skills: dict[int, set[int]]) -> None:
    """Apply weekly rust to all untrained skills.

    Args:
        trained_skills: Dict from process_weekly_training() mapping
            character PKs to sets of Skill PKs that were active this week.
    """
    all_skill_values = CharacterSkillValue.objects.select_related(
        "character",
    ).all()

    for sv in all_skill_values:
        active_skills = trained_skills.get(sv.character.pk, set())
        if sv.skill_id in active_skills:
            continue

        char_level = _get_path_level(sv.character)
        rust_amount = char_level + 5
        max_rust = _development_cost(sv.value)
        sv.rust_points = min(sv.rust_points + rust_amount, max_rust)
        sv.save()
```

Update `_apply_development_to_skill` to pay off rust first:

```python
def _apply_development_to_skill(
    skill_value: CharacterSkillValue,
    dev_points: int,
) -> None:
    if _is_at_xp_boundary(skill_value.value):
        return

    # Pay off rust first
    remaining = dev_points
    if skill_value.rust_points > 0:
        if remaining >= skill_value.rust_points:
            remaining -= skill_value.rust_points
            skill_value.rust_points = 0
        else:
            skill_value.rust_points -= remaining
            remaining = 0

    remaining += skill_value.development_points

    while remaining > 0:
        if _is_at_xp_boundary(skill_value.value):
            remaining = 0
            break

        cost = _development_cost(skill_value.value)
        if remaining >= cost:
            remaining -= cost
            skill_value.value += 1
        else:
            break

    skill_value.development_points = remaining
    skill_value.save()
```

**Step 4: Run tests**

```bash
echo "yes" | arx test world.skills.tests.test_training.ApplyWeeklyRustTests
```

**Step 5: Lint and commit**

---

### Task 9: Integration — `run_weekly_skill_cron`

**Files:**
- Modify: `src/world/skills/services.py` (add orchestrator function)
- Modify: `src/world/skills/tests/test_training.py` (add integration test)

**Context:** A single entry point that runs both training and rust in sequence. This is what the actual cron job will call.

**Step 1: Write integration test**

```python
from world.skills.services import run_weekly_skill_cron


class RunWeeklySkillCronTests(TestCase):
    """Integration test for the full weekly cron cycle."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.trained_skill = SkillFactory()
        cls.untrained_skill = SkillFactory()
        cls.trained_sv = CharacterSkillValueFactory(
            character=cls.character, skill=cls.trained_skill, value=10,
        )
        cls.untrained_sv = CharacterSkillValueFactory(
            character=cls.character, skill=cls.untrained_skill, value=11,
        )
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=cls.character, level=1)

    def test_trains_and_rusts(self) -> None:
        """Trained skill advances, untrained skill gets rust."""
        TrainingAllocation.objects.create(
            character=self.character,
            skill=self.trained_skill,
            ap_amount=20,
        )
        run_weekly_skill_cron()
        self.trained_sv.refresh_from_db()
        self.untrained_sv.refresh_from_db()
        # Trained: 5*20*1 = 100 dev. 10->11 costs 100. Level up!
        self.assertEqual(self.trained_sv.value, 11)
        self.assertEqual(self.trained_sv.rust_points, 0)
        # Untrained: level 1 + 5 = 6 rust
        self.assertEqual(self.untrained_sv.rust_points, 6)
```

**Step 2: Write the orchestrator**

```python
def run_weekly_skill_cron() -> None:
    """Run the full weekly skill development cycle.

    1. Process all training allocations (award dev points, consume AP).
    2. Apply rust to all untrained skills.
    """
    trained_skills = process_weekly_training()
    apply_weekly_rust(trained_skills)
```

**Step 3: Run all tests**

```bash
echo "yes" | arx test world.skills.tests.test_training
```

**Step 4: Lint and commit**

---

### Task 10: Admin, Documentation, and Final Verification

**Files:**
- Modify: `src/world/skills/CLAUDE.md` (update with training system info)
- Modify: `docs/systems/INDEX.md` (add training system entry if it exists)

**Context:** Update documentation files and run the full test suite.

**Step 1: Update skills CLAUDE.md**

Add a section documenting the training system: models, service functions, formula, and integration points.

**Step 2: Run full skills test suite**

```bash
echo "yes" | arx test world.skills
```

**Step 3: Run ruff on all changed files**

```bash
ruff check src/world/skills/ src/world/relationships/helpers.py
ruff format src/world/skills/ src/world/relationships/helpers.py
```

**Step 4: Commit documentation**

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | TrainingAllocation model + model tests | `skills/models.py`, `skills/tests/test_training.py` |
| 2 | Factory + admin | `skills/factories.py`, `skills/admin.py` |
| 3 | Relationship tier stub | `relationships/helpers.py` |
| 4 | Core calculation formula | `skills/services.py` |
| 5 | Specialization calculation tests | `skills/tests/test_training.py` |
| 6 | CRUD service functions | `skills/services.py` |
| 7 | Weekly training processing | `skills/services.py` |
| 8 | Weekly rust processing | `skills/services.py` |
| 9 | Cron orchestrator | `skills/services.py` |
| 10 | Documentation + final verification | `skills/CLAUDE.md` |
