"""Tests for the training allocation system."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import GuiseFactory
from world.classes.factories import CharacterClassLevelFactory
from world.skills.factories import CharacterSkillValueFactory, SkillFactory, SpecializationFactory
from world.skills.models import TrainingAllocation
from world.skills.services import calculate_training_development


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
