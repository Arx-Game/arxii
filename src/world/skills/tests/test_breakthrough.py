"""Tests for the #2115 XP-boundary plateau fix and breakthrough purchase.

Covers the rev-2 ephemerality ruling (no banking — dev points pay rust then
dissipate at a boundary, always with a visible message) and
``purchase_skill_breakthrough`` clearing the gate so training resumes from
zero (no retroactive credit).
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_sheets.factories import CharacterSheetFactory
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import TraitRatingUnlock, TraitXPCost, XPCostChart, XPCostEntry
from world.progression.models.rewards import ExperiencePointsData
from world.skills.factories import CharacterSkillValueFactory, SkillFactory
from world.skills.services import (
    _apply_development_to_skill,
    purchase_skill_breakthrough,
    skills_at_boundary,
)


class BoundaryPlateauTests(TestCase):
    """#2115 rev-2: dev points pay rust then dissipate at a boundary, with a message."""

    def setUp(self) -> None:
        super().setUp()
        self.identity = CharacterSheetFactory()
        self.character = self.identity.character
        self.skill = SkillFactory()

    def test_boundary_rusty_skill_rust_paid_surplus_dissipates_with_message(self) -> None:
        """At a boundary, incoming dev points pay off rust; surplus dissipates loudly."""
        skill_value = CharacterSkillValueFactory(
            character=self.identity,
            skill=self.skill,
            value=19,
            development_points=0,
            rust_points=50,
        )
        message = _apply_development_to_skill(skill_value, 80)
        skill_value.refresh_from_db()
        self.assertEqual(skill_value.rust_points, 0)
        self.assertEqual(skill_value.value, 19)
        self.assertEqual(skill_value.development_points, 0)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("threshold", message.lower())

    def test_boundary_clean_skill_all_dissipates_with_message(self) -> None:
        """At a boundary with no rust, all incoming dev points dissipate loudly."""
        skill_value = CharacterSkillValueFactory(
            character=self.identity,
            skill=self.skill,
            value=19,
            development_points=0,
            rust_points=0,
        )
        message = _apply_development_to_skill(skill_value, 80)
        skill_value.refresh_from_db()
        self.assertEqual(skill_value.value, 19)
        self.assertEqual(skill_value.development_points, 0)
        self.assertIsNotNone(message)

    def test_boundary_rust_fully_absorbs_dev_points_no_message(self) -> None:
        """When rust payoff exactly consumes the award, nothing dissipates — no message."""
        skill_value = CharacterSkillValueFactory(
            character=self.identity,
            skill=self.skill,
            value=19,
            development_points=0,
            rust_points=100,
        )
        message = _apply_development_to_skill(skill_value, 60)
        skill_value.refresh_from_db()
        self.assertEqual(skill_value.rust_points, 40)
        self.assertEqual(skill_value.development_points, 0)
        self.assertIsNone(message)

    def test_overflow_on_level_up_to_boundary_dissipates_with_message(self) -> None:
        """Overflow from a level-up that lands exactly on a boundary dissipates loudly."""
        skill_value = CharacterSkillValueFactory(
            character=self.identity,
            skill=self.skill,
            value=18,
            development_points=0,
            rust_points=0,
        )
        # Cost 18->19 = (18-9)*100 = 900. Give 950: overflow of 50 lands on the boundary.
        message = _apply_development_to_skill(skill_value, 950)
        skill_value.refresh_from_db()
        self.assertEqual(skill_value.value, 19)
        self.assertEqual(skill_value.development_points, 0)
        self.assertIsNotNone(message)

    def test_not_at_boundary_unaffected(self) -> None:
        """Away from a boundary, dev points accumulate normally with no message."""
        skill_value = CharacterSkillValueFactory(
            character=self.identity,
            skill=self.skill,
            value=11,
            development_points=0,
            rust_points=0,
        )
        message = _apply_development_to_skill(skill_value, 80)
        skill_value.refresh_from_db()
        self.assertEqual(skill_value.value, 11)
        self.assertEqual(skill_value.development_points, 80)
        self.assertIsNone(message)


class SkillsAtBoundaryTests(TestCase):
    """Tests for the ``skills_at_boundary`` selector (#2115)."""

    def setUp(self) -> None:
        super().setUp()
        self.identity = CharacterSheetFactory()
        self.character = self.identity.character

    def test_empty_when_no_skills_gated(self) -> None:
        CharacterSkillValueFactory(character=self.identity, skill=SkillFactory(), value=15)
        self.assertEqual(skills_at_boundary(self.character), [])

    def test_reports_gated_skill_without_authored_unlock(self) -> None:
        skill = SkillFactory()
        CharacterSkillValueFactory(character=self.identity, skill=skill, value=19)
        prospects = skills_at_boundary(self.character)
        self.assertEqual(len(prospects), 1)
        self.assertEqual(prospects[0].skill, skill)
        self.assertEqual(prospects[0].next_rating, 20)
        self.assertFalse(prospects[0].authored)
        self.assertIsNone(prospects[0].xp_cost)

    def test_reports_authored_xp_cost(self) -> None:
        skill = SkillFactory()
        CharacterSkillValueFactory(character=self.identity, skill=skill, value=19)
        chart = XPCostChart.objects.create(name="Test Breakthrough Chart")
        XPCostEntry.objects.create(chart=chart, level=20, xp_cost=100)
        TraitXPCost.objects.create(trait=skill.trait, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=skill.trait, target_rating=20)

        prospects = skills_at_boundary(self.character)
        self.assertEqual(len(prospects), 1)
        self.assertTrue(prospects[0].authored)
        self.assertEqual(prospects[0].xp_cost, 100)


class PurchaseSkillBreakthroughTests(TestCase):
    """Tests for ``purchase_skill_breakthrough`` (#2115)."""

    def setUp(self) -> None:
        super().setUp()
        self.account = AccountDB.objects.create(username="breakthrutester", email="a@a.com")
        self.identity = CharacterSheetFactory()
        self.character = self.identity.character
        self.character.db_account = self.account
        self.character.save()
        self.skill = SkillFactory()

    def _authored_unlock(self, *, target_rating: int, xp_cost: int) -> TraitRatingUnlock:
        chart = XPCostChart.objects.create(name=f"Chart {target_rating}-{self.skill.pk}")
        XPCostEntry.objects.create(chart=chart, level=target_rating, xp_cost=xp_cost)
        TraitXPCost.objects.create(trait=self.skill.trait, cost_chart=chart)
        return TraitRatingUnlock.objects.create(trait=self.skill.trait, target_rating=target_rating)

    def _set_xp(self, *, total_earned: int) -> None:
        ExperiencePointsDataFactory(account=self.account, total_earned=total_earned, total_spent=0)

    def test_fails_when_not_at_boundary(self) -> None:
        CharacterSkillValueFactory(character=self.identity, skill=self.skill, value=15)
        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(success)
        self.assertIn("not at a breakthrough boundary", message.lower())

    def test_fails_when_no_unlock_authored(self) -> None:
        CharacterSkillValueFactory(character=self.identity, skill=self.skill, value=19)
        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(success)
        self.assertIn("no breakthrough authored", message.lower())

    def test_fails_with_insufficient_xp(self) -> None:
        CharacterSkillValueFactory(character=self.identity, skill=self.skill, value=19)
        self._authored_unlock(target_rating=20, xp_cost=100)
        self._set_xp(total_earned=50)

        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(success)
        self.assertIn("insufficient xp", message.lower())

    def test_success_clears_gate_and_resumes_from_zero(self) -> None:
        """A successful purchase clears the gate; training resumes from zero (no retroactive
        credit) even if development_points is nonzero at purchase time."""
        skill_value = CharacterSkillValueFactory(
            character=self.identity,
            skill=self.skill,
            value=19,
            development_points=0,
            rust_points=0,
        )
        self._authored_unlock(target_rating=20, xp_cost=100)
        self._set_xp(total_earned=150)

        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertTrue(success, msg=message)
        self.assertIn("breakthrough", message.lower())

        skill_value.refresh_from_db()
        self.assertEqual(skill_value.value, 20)
        self.assertEqual(skill_value.development_points, 0)

        xp_tracker = ExperiencePointsData.objects.get(account=self.account)
        self.assertEqual(xp_tracker.total_spent, 100)

        # Training resumes normally now that the gate is clear.
        post_message = _apply_development_to_skill(skill_value, 50)
        skill_value.refresh_from_db()
        self.assertIsNone(post_message)
        self.assertEqual(skill_value.development_points, 50)

    def test_duplicate_purchase_fails_once_cleared(self) -> None:
        """A second purchase attempt fails — the skill is no longer at a boundary."""
        CharacterSkillValueFactory(
            character=self.identity,
            skill=self.skill,
            value=19,
            development_points=0,
            rust_points=0,
        )
        self._authored_unlock(target_rating=20, xp_cost=100)
        self._set_xp(total_earned=300)

        first_success, _ = purchase_skill_breakthrough(self.character, self.skill)
        self.assertTrue(first_success)

        second_success, second_message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(second_success)
        self.assertIn("not at a breakthrough boundary", second_message.lower())
