"""Tests for progression actions (training allocation CRUD + unlock purchase)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from actions.definitions.progression import ManageTrainingAction, PurchaseUnlockAction
from world.action_points.factories import ActionPointConfigFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.magic.factories import ThreadFactory, ThreadXPLockedLevelFactory
from world.magic.models import ThreadLevelUnlock
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import (
    CharacterUnlock,
    ClassLevelUnlock,
    ClassXPCost,
    TraitRatingUnlock,
    TraitXPCost,
    XPCostChart,
    XPCostEntry,
)
from world.scenes.factories import PersonaFactory
from world.skills.factories import (
    CharacterSkillValueFactory,
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
        self.assertEqual(allocation.character, self.sheet)
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
        self.assertEqual(allocation.character, self.sheet)
        self.assertIsNone(allocation.skill)
        self.assertEqual(allocation.specialization, self.specialization)
        self.assertEqual(allocation.mentor, self.mentor)
        self.assertEqual(allocation.ap_amount, 15)

    def test_update_allocation(self) -> None:
        """Can update AP amount and mentor on an owned allocation."""
        allocation = TrainingAllocationFactory(
            character=self.character.sheet_data,
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
            character=self.character.sheet_data,
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
            character=self.character.sheet_data,
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
            character=self.character.sheet_data,
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
        allocation = TrainingAllocationFactory(
            character=other_sheet,
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
        allocation = TrainingAllocationFactory(
            character=other_sheet,
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


class PurchaseUnlockActionTests(TestCase):
    """Tests for PurchaseUnlockAction."""

    def _create_character_with_account(self):
        """Create a character, their sheet, and an attached account."""
        account = AccountDB.objects.create(
            username="testplayer",
            email="test@test.com",
        )
        sheet = CharacterSheetFactory()
        character = sheet.character
        character.db_account = account
        character.save()
        return character, sheet, account

    def _create_class_level_unlock(self, character, *, xp_cost: int):
        """Create a ClassLevelUnlock for ``character`` with an XP cost."""
        class_level = CharacterClassLevelFactory(character=character.sheet_data, level=3)
        class_unlock = ClassLevelUnlock.objects.create(
            character_class=class_level.character_class,
            target_level=4,
        )
        chart = XPCostChart.objects.create(name=f"Test Chart {class_unlock.pk}")
        XPCostEntry.objects.create(chart=chart, level=4, xp_cost=xp_cost)
        ClassXPCost.objects.create(
            character_class=class_level.character_class,
            cost_chart=chart,
        )
        return class_unlock

    def _set_xp(self, account, *, total_earned: int, total_spent: int = 0):
        """Create or replace the account's XP tracker with the given totals."""
        return ExperiencePointsDataFactory(
            account=account,
            total_earned=total_earned,
            total_spent=total_spent,
        )

    def test_purchase_class_level_unlock_success(self):
        """Can purchase a class-level unlock when the actor has enough XP."""
        character, _sheet, account = self._create_character_with_account()
        class_unlock = self._create_class_level_unlock(character, xp_cost=100)
        self._set_xp(account, total_earned=150)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="class_level",
            class_level_unlock_id=class_unlock.pk,
        )

        self.assertTrue(result.success)
        self.assertIn("successfully unlocked", result.message.lower())
        self.assertEqual(result.data["unlock_type"], "class_level")
        self.assertEqual(result.data["unlock_id"], CharacterUnlock.objects.get().pk)

    def test_purchase_class_level_insufficient_xp(self):
        """Purchasing a class-level unlock fails without enough XP."""
        character, _sheet, account = self._create_character_with_account()
        class_unlock = self._create_class_level_unlock(character, xp_cost=100)
        self._set_xp(account, total_earned=50)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="class_level",
            class_level_unlock_id=class_unlock.pk,
        )

        self.assertFalse(result.success)
        self.assertIn("insufficient xp", result.message.lower())

    def test_purchase_thread_xp_lock_success(self):
        """Can purchase a thread XP-lock boundary the actor owns."""
        character, sheet, account = self._create_character_with_account()
        # Path stage 2 -> path cap 20; trait value 30 -> anchor cap 30.
        # Effective cap is 20, so boundary level 20 is purchasable.
        thread = ThreadFactory(
            owner=sheet,
            _trait_value=30,
            _path_stage=2,
        )
        ThreadXPLockedLevelFactory(level=20, xp_cost=100)
        self._set_xp(account, total_earned=150)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="thread_xp_lock",
            thread_id=thread.pk,
            boundary_level=20,
        )

        self.assertTrue(result.success)
        self.assertIn("unlocked", result.message.lower())
        self.assertEqual(result.data["unlock_type"], "thread_xp_lock")
        self.assertEqual(result.data["thread_id"], thread.pk)
        self.assertEqual(result.data["boundary_level"], 20)
        self.assertEqual(
            result.data["thread_level_unlock_id"],
            ThreadLevelUnlock.objects.get(thread=thread, unlocked_level=20).pk,
        )

    def test_purchase_thread_not_owned(self):
        """Cannot purchase a thread XP-lock boundary for someone else's thread."""
        character, _sheet, account = self._create_character_with_account()
        other_sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=other_sheet)
        ThreadXPLockedLevelFactory(level=20, xp_cost=100)
        self._set_xp(account, total_earned=150)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="thread_xp_lock",
            thread_id=thread.pk,
            boundary_level=20,
        )

        self.assertFalse(result.success)
        self.assertIn("own threads", result.message.lower())
        self.assertIsNone(
            ThreadLevelUnlock.objects.filter(thread=thread, unlocked_level=20).first()
        )

    def test_purchase_thread_xp_lock_missing_boundary_level(self):
        """A missing boundary_level returns a clean failure, not a TypeError."""
        character, sheet, account = self._create_character_with_account()
        thread = ThreadFactory(owner=sheet)
        self._set_xp(account, total_earned=150)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="thread_xp_lock",
            thread_id=thread.pk,
        )

        self.assertFalse(result.success)
        self.assertIn("boundary_level is required", result.message.lower())

    def test_purchase_thread_xp_lock_missing_thread_id(self):
        """A missing thread_id returns a clean failure, not a ValueError."""
        character, _sheet, account = self._create_character_with_account()
        self._set_xp(account, total_earned=150)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="thread_xp_lock",
            boundary_level=20,
        )

        self.assertFalse(result.success)
        self.assertIn("thread_id is required", result.message.lower())

    def test_purchase_class_level_unlock_missing_id(self):
        """A missing class_level_unlock_id returns a clean failure."""
        character, _sheet, _account = self._create_character_with_account()

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="class_level",
        )

        self.assertFalse(result.success)
        self.assertIn("class_level_unlock_id is required", result.message.lower())

    def _authored_skill_breakthrough(self, skill, *, target_rating: int, xp_cost: int):
        """Author a TraitRatingUnlock + its XP cost for ``skill`` (#2115)."""
        chart = XPCostChart.objects.create(name=f"Breakthrough Chart {skill.pk}")
        XPCostEntry.objects.create(chart=chart, level=target_rating, xp_cost=xp_cost)
        TraitXPCost.objects.create(trait=skill.trait, cost_chart=chart)
        return TraitRatingUnlock.objects.create(trait=skill.trait, target_rating=target_rating)

    def test_purchase_skill_breakthrough_success(self):
        """Can purchase a skill breakthrough when the actor has enough XP (#2115)."""
        character, _sheet, account = self._create_character_with_account()
        skill = SkillFactory()
        skill_value = CharacterSkillValueFactory(
            character=character.sheet_data, skill=skill, value=19
        )
        self._authored_skill_breakthrough(skill, target_rating=20, xp_cost=100)
        self._set_xp(account, total_earned=150)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="skill_breakthrough",
            skill_id=skill.pk,
        )

        self.assertTrue(result.success)
        self.assertIn("breakthrough", result.message.lower())
        self.assertEqual(result.data["unlock_type"], "skill_breakthrough")
        self.assertEqual(result.data["skill_id"], skill.pk)
        skill_value.refresh_from_db()
        self.assertEqual(skill_value.value, 20)

    def test_purchase_skill_breakthrough_insufficient_xp(self):
        """Purchasing a skill breakthrough fails without enough XP (#2115)."""
        character, _sheet, account = self._create_character_with_account()
        skill = SkillFactory()
        CharacterSkillValueFactory(character=character.sheet_data, skill=skill, value=19)
        self._authored_skill_breakthrough(skill, target_rating=20, xp_cost=100)
        self._set_xp(account, total_earned=50)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="skill_breakthrough",
            skill_id=skill.pk,
        )

        self.assertFalse(result.success)
        self.assertIn("insufficient xp", result.message.lower())

    def test_purchase_skill_breakthrough_duplicate_fails(self):
        """A second purchase attempt fails once the gate is already cleared (#2115)."""
        character, _sheet, account = self._create_character_with_account()
        skill = SkillFactory()
        CharacterSkillValueFactory(character=character.sheet_data, skill=skill, value=19)
        self._authored_skill_breakthrough(skill, target_rating=20, xp_cost=100)
        self._set_xp(account, total_earned=300)

        first = PurchaseUnlockAction().run(
            actor=character, unlock_type="skill_breakthrough", skill_id=skill.pk
        )
        self.assertTrue(first.success)

        second = PurchaseUnlockAction().run(
            actor=character, unlock_type="skill_breakthrough", skill_id=skill.pk
        )
        self.assertFalse(second.success)
        self.assertIn("not at a breakthrough boundary", second.message.lower())

    def test_purchase_skill_breakthrough_missing_skill_id(self):
        """A missing skill_id returns a clean failure, not a TypeError (#2115)."""
        character, _sheet, _account = self._create_character_with_account()

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="skill_breakthrough",
        )

        self.assertFalse(result.success)
        self.assertIn("skill_id is required", result.message.lower())

    def test_purchase_skill_breakthrough_unknown_skill_id(self):
        """An unknown skill_id returns a clean failure, not a raw DoesNotExist (#2115)."""
        character, _sheet, account = self._create_character_with_account()
        self._set_xp(account, total_earned=150)

        result = PurchaseUnlockAction().run(
            actor=character,
            unlock_type="skill_breakthrough",
            skill_id=999999,
        )

        self.assertFalse(result.success)
