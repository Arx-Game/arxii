"""Tests for the training allocation system."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import GuiseFactory
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import TrainingAllocation


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
