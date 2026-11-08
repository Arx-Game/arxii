"""Tests for the #2115 XP-boundary plateau fix and breakthrough purchase.

Covers the rev-2 ephemerality ruling (no banking — dev points pay rust then
dissipate at a boundary, always with a visible message) and
``purchase_skill_breakthrough`` clearing the gate so training resumes from
zero (no retroactive credit).
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.sheet_writers import set_skill_values
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import TraitRatingUnlock, TraitXPCost, XPCostChart, XPCostEntry
from world.progression.models.rewards import (
    DevelopmentPoints,
    ExperiencePointsData,
    cumulative_dp_for_level,
)
from world.roster.factories import grant_test_tenure
from world.skills.factories import SkillFactory, SkillRatingFactory
from world.skills.services import (
    purchase_skill_breakthrough,
    skills_at_boundary,
    train_skill,
)


class BoundaryPlateauTests(TestCase):
    """#2115 rev-2: dev points pay rust then dissipate at a boundary, with a message.

    Training develops the skill trait's ``DevelopmentPoints`` ledger (#5010).
    """

    def setUp(self) -> None:
        super().setUp()
        self.identity = CharacterSheetFactory()
        self.skill = SkillFactory()

    def _train(self, value: int, points: int, *, rust: int = 0) -> tuple[str | None, int]:
        """Rate the skill ``value`` with ``rust`` owed, train ``points``; message, new value."""
        set_skill_values(self.identity, {self.skill: value}, {}, source="test")
        tracker = self._tracker()
        tracker.rust_debt = rust
        tracker.save(update_fields=["rust_debt"])
        result = train_skill(self.identity, self.skill, points, description="x")
        return result.plateau_message, result.new_value

    def _tracker(self) -> DevelopmentPoints:
        return DevelopmentPoints.objects.get(character_sheet=self.identity, trait=self.skill)

    def test_boundary_rusty_skill_rust_paid_surplus_dissipates_with_message(self) -> None:
        """At a boundary, incoming dev points pay off rust; surplus dissipates loudly."""
        message, value = self._train(19, 80, rust=50)
        self.assertEqual(value, 19)
        self.assertEqual(self._tracker().rust_debt, 0)
        self.assertEqual(self._tracker().total_earned, cumulative_dp_for_level(19))
        assert message is not None
        self.assertIn("threshold", message.lower())

    def test_boundary_clean_skill_all_dissipates_with_message(self) -> None:
        """At a boundary with no rust, all incoming dev points dissipate loudly."""
        message, value = self._train(19, 80)
        self.assertEqual(value, 19)
        self.assertEqual(self._tracker().total_earned, cumulative_dp_for_level(19))
        self.assertIsNotNone(message)

    def test_boundary_rust_fully_absorbs_dev_points_no_message(self) -> None:
        """When rust payoff exactly consumes the award, nothing dissipates — no message."""
        message, _value = self._train(19, 60, rust=100)
        self.assertEqual(self._tracker().rust_debt, 40)
        self.assertIsNone(message)

    def test_overflow_on_level_up_to_boundary_dissipates_with_message(self) -> None:
        """Overflow from a level-up that lands exactly on a boundary dissipates loudly."""
        # Cost 18->19 = (18-9)*100 = 900. Give 950: overflow of 50 lands on the boundary.
        message, value = self._train(18, 950)
        self.assertEqual(value, 19)
        self.assertEqual(self._tracker().total_earned, cumulative_dp_for_level(19))
        self.assertIsNotNone(message)

    def test_not_at_boundary_unaffected(self) -> None:
        """Away from a boundary, dev points accumulate normally with no message."""
        message, value = self._train(11, 80)
        self.assertEqual(value, 11)
        self.assertEqual(self._tracker().total_earned, cumulative_dp_for_level(11) + 80)
        self.assertIsNone(message)


class SkillsAtBoundaryTests(TestCase):
    """Tests for the ``skills_at_boundary`` selector (#2115)."""

    def setUp(self) -> None:
        super().setUp()
        self.identity = CharacterSheetFactory()
        self.character = self.identity.character

    def test_empty_when_no_skills_gated(self) -> None:
        set_skill_values(self.identity, {SkillFactory(): 15}, {}, source="test")
        self.assertEqual(skills_at_boundary(self.character), [])

    def test_reports_gated_skill_without_authored_unlock(self) -> None:
        skill = SkillFactory()
        set_skill_values(self.identity, {skill: 19}, {}, source="test")
        prospects = skills_at_boundary(self.character)
        self.assertEqual(len(prospects), 1)
        self.assertEqual(prospects[0].skill, skill)
        self.assertEqual(prospects[0].next_rating, 20)
        self.assertFalse(prospects[0].authored)
        self.assertIsNone(prospects[0].xp_cost)

    def test_reports_authored_xp_cost(self) -> None:
        skill = SkillFactory()
        set_skill_values(self.identity, {skill: 19}, {}, source="test")
        chart = XPCostChart.objects.create(name="Test Breakthrough Chart")
        XPCostEntry.objects.create(chart=chart, level=20, xp_cost=100)
        TraitXPCost.objects.create(trait=skill, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=skill, target_rating=20)

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
        grant_test_tenure(self.identity, self.account)
        self.skill = SkillFactory()

    def _authored_unlock(self, *, target_rating: int, xp_cost: int) -> TraitRatingUnlock:
        chart = XPCostChart.objects.create(name=f"Chart {target_rating}-{self.skill.pk}")
        XPCostEntry.objects.create(chart=chart, level=target_rating, xp_cost=xp_cost)
        TraitXPCost.objects.create(trait=self.skill, cost_chart=chart)
        return TraitRatingUnlock.objects.create(trait=self.skill, target_rating=target_rating)

    def _set_xp(self, *, total_earned: int) -> None:
        ExperiencePointsDataFactory(account=self.account, total_earned=total_earned, total_spent=0)

    def test_fails_when_not_at_boundary(self) -> None:
        SkillRatingFactory(character=self.identity, skill=self.skill, value=15)
        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(success)
        self.assertIn("not at a breakthrough boundary", message.lower())

    def test_fails_when_no_unlock_authored(self) -> None:
        SkillRatingFactory(character=self.identity, skill=self.skill, value=19)
        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(success)
        self.assertIn("no breakthrough authored", message.lower())

    def test_fails_with_insufficient_xp(self) -> None:
        SkillRatingFactory(character=self.identity, skill=self.skill, value=19)
        self._authored_unlock(target_rating=20, xp_cost=100)
        self._set_xp(total_earned=50)

        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(success)
        self.assertIn("insufficient xp", message.lower())

    def test_success_clears_gate_and_resumes_from_zero(self) -> None:
        """A successful purchase clears the gate and raises the ledger to the new rating;
        training resumes from zero toward the next level (no retroactive credit)."""
        skill_value = SkillRatingFactory(
            character=self.identity,
            skill=self.skill,
            value=19,
        )
        self._authored_unlock(target_rating=20, xp_cost=100)
        self._set_xp(total_earned=150)

        success, message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertTrue(success, msg=message)
        self.assertIn("breakthrough", message.lower())

        skill_value.refresh_from_db()
        self.assertEqual(skill_value.value, 20)
        tracker = DevelopmentPoints.objects.get(character_sheet=self.identity, trait=self.skill)
        self.assertEqual(tracker.total_earned, cumulative_dp_for_level(20))

        xp_tracker = ExperiencePointsData.objects.get(account=self.account)
        self.assertEqual(xp_tracker.total_spent, 100)

        # Training resumes normally now that the gate is clear.
        result = train_skill(self.identity, self.skill, 50, description="x")
        self.assertIsNone(result.plateau_message)
        self.assertEqual(tracker.total_earned, cumulative_dp_for_level(20) + 50)

    def test_duplicate_purchase_fails_once_cleared(self) -> None:
        """A second purchase attempt fails — the skill is no longer at a boundary."""
        SkillRatingFactory(
            character=self.identity,
            skill=self.skill,
            value=19,
        )
        self._authored_unlock(target_rating=20, xp_cost=100)
        self._set_xp(total_earned=300)

        first_success, _ = purchase_skill_breakthrough(self.character, self.skill)
        self.assertTrue(first_success)

        second_success, second_message = purchase_skill_breakthrough(self.character, self.skill)
        self.assertFalse(second_success)
        self.assertIn("not at a breakthrough boundary", second_message.lower())
