"""Tests for the training allocation system."""

from django.db import IntegrityError
from django.test import TestCase

from world.action_points.models import ActionPointConfig
from world.character_sheets.factories import GuiseFactory
from world.classes.factories import CharacterClassLevelFactory
from world.skills.factories import (
    CharacterSkillValueFactory,
    CharacterSpecializationValueFactory,
    SkillFactory,
    SpecializationFactory,
)
from world.skills.models import TrainingAllocation
from world.skills.services import (
    calculate_training_development,
    create_training_allocation,
    remove_training_allocation,
    update_training_allocation,
)


class TrainingAllocationModelTests(TestCase):
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

    def test_rejects_both_skill_and_specialization(self) -> None:
        """Cannot set both skill and specialization."""
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                skill=self.skill,
                specialization=self.specialization,
                ap_amount=10,
            )

    def test_rejects_neither_skill_nor_specialization(self) -> None:
        """Must set either skill or specialization."""
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                ap_amount=10,
            )


class CalculateTrainingDevelopmentTests(TestCase):
    """Tests for calculate_training_development formula."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.student_guise = GuiseFactory()
        cls.student = cls.student_guise.character
        cls.skill = SkillFactory()

        # Student has skill value 40
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

        # Teaching skill for mentor (value=20)
        cls.teaching_skill = SkillFactory()
        cls.teaching_skill.trait.name = "Teaching"
        cls.teaching_skill.trait.save()
        CharacterSkillValueFactory(
            character=cls.mentor,
            skill=cls.teaching_skill,
            value=20,
        )

        # Path level for student = 5
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

    def test_zero_student_skill_uses_floor(self) -> None:
        """Student with 0 skill uses 1 to prevent division by zero."""
        student_guise = GuiseFactory()
        student = student_guise.character
        # No CharacterSkillValue created — defaults to 0 -> floor to 1
        CharacterClassLevelFactory(character=student, level=1)
        alloc = TrainingAllocation.objects.create(
            character=student,
            skill=self.skill,
            mentor=self.mentor_guise,
            ap_amount=10,
        )
        result = calculate_training_development(alloc)
        # base = 5 * 10 * 1 = 50
        # mentor_total = 100 + 20 = 120
        # student_total = 0 -> 1
        # ratio = 120
        # effective_AP = 10 + 20 = 30
        # mentor_bonus = 30 * 120 * 1 = 3600
        # total = 50 + 3600 = 3650
        self.assertEqual(result, 3650)


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
            character=cls.student,
            specialization=cls.spec,
            value=10,
        )

        # Mentor: parent=50, spec=50, teaching=20
        cls.mentor_guise = GuiseFactory()
        cls.mentor = cls.mentor_guise.character
        CharacterSkillValueFactory(character=cls.mentor, skill=cls.skill, value=50)
        CharacterSpecializationValueFactory(
            character=cls.mentor,
            specialization=cls.spec,
            value=50,
        )
        cls.teaching_skill = SkillFactory()
        cls.teaching_skill.trait.name = "Teaching"
        cls.teaching_skill.trait.save()
        CharacterSkillValueFactory(
            character=cls.mentor,
            skill=cls.teaching_skill,
            value=20,
        )

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
        config = ActionPointConfig.get_active()
        budget = config.weekly_regen if config else 100
        create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=budget,
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
        config = ActionPointConfig.get_active()
        budget = config.weekly_regen if config else 100
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=budget,
        )
        with self.assertRaises(ValueError):
            update_training_allocation(alloc, ap_amount=budget + 1)


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
        self.assertFalse(TrainingAllocation.objects.filter(pk=alloc.pk).exists())
