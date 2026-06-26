"""Tests for progression actions (training allocation CRUD)."""

from django.test import TestCase

from actions.definitions.progression import ManageTrainingAction
from world.action_points.factories import ActionPointConfigFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory
from world.skills.factories import (
    SkillFactory,
    SpecializationFactory,
    TrainingAllocationFactory,
)
from world.skills.models import TrainingAllocation


class ManageTrainingActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.skill = SkillFactory()
        cls.specialization = SpecializationFactory()
        cls.mentor = PersonaFactory()
        cls.config = ActionPointConfigFactory(weekly_regen=100)

    def test_add_skill_allocation(self) -> None:
        """Can add a training allocation for a skill."""
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="add",
            skill_id=self.skill.pk,
            ap_amount=20,
        )
        self.assertTrue(result.success)
        allocation = TrainingAllocation.objects.get(pk=result.data["allocation_id"])
        self.assertEqual(allocation.character, self.character)
        self.assertEqual(allocation.skill, self.skill)
        self.assertIsNone(allocation.specialization)
        self.assertIsNone(allocation.mentor)
        self.assertEqual(allocation.ap_amount, 20)

    def test_add_specialization_allocation(self) -> None:
        """Can add a training allocation for a specialization."""
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="add",
            specialization_id=self.specialization.pk,
            ap_amount=15,
            mentor_persona_id=self.mentor.pk,
        )
        self.assertTrue(result.success)
        allocation = TrainingAllocation.objects.get(pk=result.data["allocation_id"])
        self.assertEqual(allocation.character, self.character)
        self.assertIsNone(allocation.skill)
        self.assertEqual(allocation.specialization, self.specialization)
        self.assertEqual(allocation.mentor, self.mentor)
        self.assertEqual(allocation.ap_amount, 15)

    def test_update_allocation(self) -> None:
        """Can update AP amount and mentor on an owned allocation."""
        allocation = TrainingAllocationFactory(
            character=self.character,
            skill=self.skill,
            ap_amount=10,
        )
        new_mentor = PersonaFactory()
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="update",
            allocation_id=allocation.pk,
            ap_amount=25,
            mentor_persona_id=new_mentor.pk,
        )
        self.assertTrue(result.success)
        allocation.refresh_from_db()
        self.assertEqual(allocation.ap_amount, 25)
        self.assertEqual(allocation.mentor, new_mentor)

    def test_update_removes_mentor_when_none(self) -> None:
        """Passing mentor_persona_id=None clears the mentor."""
        allocation = TrainingAllocationFactory(
            character=self.character,
            skill=self.skill,
            ap_amount=10,
            mentor=self.mentor,
        )
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="update",
            allocation_id=allocation.pk,
            mentor_persona_id=None,
        )
        self.assertTrue(result.success)
        allocation.refresh_from_db()
        self.assertIsNone(allocation.mentor)

    def test_remove_allocation(self) -> None:
        """Can remove an owned training allocation."""
        allocation = TrainingAllocationFactory(
            character=self.character,
            skill=self.skill,
            ap_amount=10,
        )
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="remove",
            allocation_id=allocation.pk,
        )
        self.assertTrue(result.success)
        self.assertFalse(TrainingAllocation.objects.filter(pk=allocation.pk).exists())

    def test_rejects_both_skill_and_specialization(self) -> None:
        """Add requires exactly one of skill_id or specialization_id."""
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="add",
            skill_id=self.skill.pk,
            specialization_id=self.specialization.pk,
            ap_amount=10,
        )
        self.assertFalse(result.success)
        self.assertIn("exactly one", result.message.lower())

    def test_rejects_neither_skill_nor_specialization(self) -> None:
        """Add requires one of skill_id or specialization_id."""
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="add",
            ap_amount=10,
        )
        self.assertFalse(result.success)
        self.assertIn("exactly one", result.message.lower())

    def test_rejects_exceeding_weekly_budget(self) -> None:
        """Add fails when total allocated AP would exceed weekly budget."""
        skill2 = SkillFactory()
        ManageTrainingAction().run(
            actor=self.character,
            operation="add",
            skill_id=self.skill.pk,
            ap_amount=100,
        )
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="add",
            skill_id=skill2.pk,
            ap_amount=1,
        )
        self.assertFalse(result.success)
        self.assertIn("budget", result.message.lower())

    def test_rejects_update_exceeding_budget(self) -> None:
        """Update fails when new total would exceed weekly budget."""
        budget = self.config.weekly_regen
        allocation = TrainingAllocationFactory(
            character=self.character,
            skill=self.skill,
            ap_amount=budget,
        )
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="update",
            allocation_id=allocation.pk,
            ap_amount=budget + 1,
        )
        self.assertFalse(result.success)
        self.assertIn("budget", result.message.lower())

    def test_rejects_update_of_foreign_allocation(self) -> None:
        """A character cannot update another character's allocation."""
        other_sheet = CharacterSheetFactory()
        other_character = other_sheet.character
        allocation = TrainingAllocationFactory(
            character=other_character,
            skill=self.skill,
            ap_amount=10,
        )
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="update",
            allocation_id=allocation.pk,
            ap_amount=5,
        )
        self.assertFalse(result.success)
        self.assertIn("own", result.message.lower())

    def test_rejects_remove_of_foreign_allocation(self) -> None:
        """A character cannot remove another character's allocation."""
        other_sheet = CharacterSheetFactory()
        other_character = other_sheet.character
        allocation = TrainingAllocationFactory(
            character=other_character,
            skill=self.skill,
            ap_amount=10,
        )
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="remove",
            allocation_id=allocation.pk,
        )
        self.assertFalse(result.success)
        self.assertIn("own", result.message.lower())

    def test_rejects_unknown_allocation_id(self) -> None:
        """Update fails for a nonexistent allocation."""
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="update",
            allocation_id=999999,
        )
        self.assertFalse(result.success)

    def test_rejects_unknown_skill_id(self) -> None:
        """Add fails for a nonexistent skill."""
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="add",
            skill_id=999999,
            ap_amount=10,
        )
        self.assertFalse(result.success)

    def test_rejects_invalid_operation(self) -> None:
        """An unknown operation returns a failure result."""
        result = ManageTrainingAction().run(
            actor=self.character,
            operation="foo",
        )
        self.assertFalse(result.success)
