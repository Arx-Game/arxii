"""Worship rites (#3777): cost, tiered payout, multipliers and the weekly favor cap.

Checks are forced through ``world.checks.test_helpers.force_check_outcome``,
the official seam; everything else is the real service path.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.worship import PerformWorshipRiteAction
from evennia_extensions.factories import ObjectDBFactory
from world.action_points.factories import ActionPointPoolFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.magic.constants import GainSource
from world.magic.models import CharacterResonance
from world.magic.models.grant import ResonanceGrant
from world.roster.factories import grant_test_tenure
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import BeingResonanceTier, RiteTier
from world.worship.exceptions import (
    RiteActionPointsInsufficient,
    RiteAwardMissing,
    RiteIsCeremony,
    RiteScenePrerequisiteFailed,
)
from world.worship.factories import (
    BeingResonanceFactory,
    RiteKindFactory,
    WorshipFeastDayFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
)
from world.worship.models import DevotionStanding, WorshipRitePerformance
from world.worship.rite_services import perform_worship_rite, rite_ap_cost


class RiteTestBase(TestCase):
    """A performer in a live scene, a tier 1 rite on an ASSOCIATED resonance,
    and one award row for the forced outcome."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.tenure = grant_test_tenure(cls.sheet)
        cls.account = cls.tenure.player_data.account
        cls.room = ObjectDBFactory(db_key="Chapel", db_typeclass_path="typeclasses.rooms.Room")
        cls.character.db_location = cls.room
        cls.character.save(update_fields=["db_location"])
        cls.scene = SceneFactory(location=cls.room, is_active=True)
        SceneParticipationFactory(scene=cls.scene, account=cls.account)
        cls.pool = ActionPointPoolFactory(character=cls.sheet, current=10, maximum=10)

        cls.kind = RiteKindFactory(name="Vigil", tier=RiteTier.DEVOTIONAL)
        cls.rite = WorshipRiteFactory(kind=cls.kind, name="The Long Watch")
        cls.rite.resonance.tier = BeingResonanceTier.ASSOCIATED
        cls.rite.resonance.save(update_fields=["tier"])
        cls.being = cls.rite.being
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.award = WorshipRiteTierAwardFactory(
            tier=RiteTier.DEVOTIONAL, outcome_tier=cls.success, resonance_amount=4, favor_amount=2
        )

    def _perform(self, outcome=None):
        with force_check_outcome(outcome or self.success):
            return perform_worship_rite(self.sheet, self.rite, scene=self.scene)

    def _balance(self) -> int:
        row = CharacterResonance.objects.filter(
            character_sheet=self.sheet, resonance=self.rite.resonance.resonance
        ).first()
        return row.balance if row is not None else 0

    def _favor(self) -> int:
        row = DevotionStanding.objects.filter(character_sheet=self.sheet, being=self.being).first()
        return row.favor if row is not None else 0


class PerformRiteTests(RiteTestBase):
    def test_pays_the_tier_award_and_records_the_performance(self) -> None:
        outcome = self._perform()

        self.assertEqual(outcome.resonance_granted, 4)
        self.assertEqual(outcome.favor_granted, 2)
        self.assertEqual(self._balance(), 4)
        self.assertEqual(self._favor(), 2)
        performance = WorshipRitePerformance.objects.get(character_sheet=self.sheet)
        self.assertEqual(performance.rite, self.rite)
        self.assertEqual(performance.scene, self.scene)
        self.assertEqual(performance.outcome_tier, self.success)
        grant = ResonanceGrant.objects.get(character_sheet=self.sheet)
        self.assertEqual(grant.source, GainSource.WORSHIP_RITE)
        self.assertEqual(grant.source_worship_rite_performance, performance)

    def test_costs_one_ap_per_tier_and_some_social_fatigue(self) -> None:
        from world.fatigue.services import get_or_create_fatigue_pool

        before = get_or_create_fatigue_pool(self.sheet).get_current("social")
        self.assertEqual(rite_ap_cost(self.rite), 1)

        self._perform()

        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 9)
        self.assertGreater(get_or_create_fatigue_pool(self.sheet).get_current("social"), before)

    def test_tier_two_costs_two_ap(self) -> None:
        self.kind.tier = RiteTier.DEMANDING
        self.kind.save(update_fields=["tier"])
        WorshipRiteTierAwardFactory(
            tier=RiteTier.DEMANDING, outcome_tier=self.success, resonance_amount=8, favor_amount=6
        )

        outcome = self._perform()

        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 8)
        self.assertEqual(outcome.resonance_granted, 8)

    def test_insufficient_ap_refuses_before_rolling(self) -> None:
        self.pool.current = 0
        self.pool.save(update_fields=["current"])

        with self.assertRaises(RiteActionPointsInsufficient):
            self._perform()
        self.assertFalse(WorshipRitePerformance.objects.exists())

    def test_favor_is_capped_once_per_rite_per_week_but_resonance_is_not(self) -> None:
        self._perform()
        second = self._perform()

        self.assertEqual(second.resonance_granted, 4)
        self.assertEqual(second.favor_granted, 0)
        self.assertTrue(second.favor_capped)
        self.assertEqual(self._balance(), 8)
        self.assertEqual(self._favor(), 2)

    def test_a_different_rite_earns_its_own_favor_the_same_week(self) -> None:
        self._perform()
        other = WorshipRiteFactory(being=self.being, kind=self.kind, name="The Short Watch")
        other.resonance.tier = BeingResonanceTier.ASSOCIATED
        other.resonance.save(update_fields=["tier"])

        with force_check_outcome(self.success):
            outcome = perform_worship_rite(self.sheet, other, scene=self.scene)

        self.assertEqual(outcome.favor_granted, 2)
        self.assertEqual(self._favor(), 4)

    def test_favored_resonance_pays_double(self) -> None:
        self.rite.resonance.tier = BeingResonanceTier.FAVORED
        self.rite.resonance.save(update_fields=["tier"])

        outcome = self._perform()

        self.assertEqual(outcome.multiplier_percent, 200)
        self.assertEqual(outcome.resonance_granted, 8)
        self.assertEqual(outcome.favor_granted, 4)

    def test_feast_day_doubles(self) -> None:
        WorshipFeastDayFactory(being=self.being, ic_month=3, ic_day=9)

        with patch("world.worship.rite_services.is_feast_day_today", return_value=True):
            outcome = self._perform()

        self.assertEqual(outcome.multiplier_percent, 200)
        self.assertEqual(outcome.resonance_granted, 8)

    def test_birth_favor_doubles_and_stacks_with_a_favored_resonance(self) -> None:
        self.rite.resonance.tier = BeingResonanceTier.FAVORED
        self.rite.resonance.save(update_fields=["tier"])

        with patch("world.worship.services.is_birth_favored_by", return_value=True):
            outcome = self._perform()

        self.assertEqual(outcome.multiplier_percent, 400)
        self.assertEqual(outcome.resonance_granted, 16)

    def test_no_feast_day_today_is_no_multiplier(self) -> None:
        outcome = self._perform()
        self.assertEqual(outcome.multiplier_percent, 100)

    def test_tier_three_is_a_ceremony_not_a_solo_act(self) -> None:
        self.kind.tier = RiteTier.PERILOUS
        self.kind.save(update_fields=["tier"])

        with self.assertRaises(RiteIsCeremony):
            self._perform()

    def test_needs_a_live_scene_the_performer_entered(self) -> None:
        stranger = CharacterSheetFactory()
        grant_test_tenure(stranger)
        ActionPointPoolFactory(character=stranger)

        with self.assertRaises(RiteScenePrerequisiteFailed), force_check_outcome(self.success):
            perform_worship_rite(stranger, self.rite, scene=self.scene)

        self.scene.is_active = False
        self.scene.save(update_fields=["is_active"])
        with self.assertRaises(RiteScenePrerequisiteFailed):
            self._perform()

    def test_missing_award_row_raises_and_rolls_back(self) -> None:
        botch = CheckOutcomeFactory(name="Critical Failure", success_level=-2)

        with self.assertRaises(RiteAwardMissing):
            self._perform(botch)

        self.assertFalse(WorshipRitePerformance.objects.exists())
        # Read the row, not the identity-mapped instance: a rolled-back atomic
        # block restores the DB but leaves the cached object holding the spend.
        stored = (
            ActionPointPool.objects.filter(pk=self.pool.pk).values_list("current", flat=True).get()
        )
        self.assertEqual(stored, 10)  # the atomic block refunded the cost

    def test_rite_must_channel_its_own_beings_resonance(self) -> None:
        from django.core.exceptions import ValidationError

        foreign = BeingResonanceFactory()
        self.rite.resonance = foreign
        with self.assertRaises(ValidationError):
            self.rite.full_clean()


class PerformRiteActionTests(RiteTestBase):
    def test_action_resolves_the_rite_by_name_and_reports_the_payout(self) -> None:
        with force_check_outcome(self.success):
            result = PerformWorshipRiteAction().run(
                actor=self.character, rite_name="the long watch"
            )

        self.assertTrue(result.success, result.message)
        self.assertIn("The Long Watch", result.message)
        self.assertIn("+4", result.message)
        self.assertEqual(result.data["favor_granted"], 2)

    def test_action_reports_a_capped_week_plainly(self) -> None:
        self._perform()

        with force_check_outcome(self.success):
            result = PerformWorshipRiteAction().run(actor=self.character, rite=self.rite)

        self.assertTrue(result.success)
        self.assertTrue(result.data["favor_capped"])
        self.assertIn("already marked", result.message)

    def test_action_outside_a_scene_fails_softly(self) -> None:
        elsewhere = ObjectDBFactory(db_key="Alley", db_typeclass_path="typeclasses.rooms.Room")
        self.character.db_location = elsewhere
        self.character.save(update_fields=["db_location"])

        result = PerformWorshipRiteAction().run(actor=self.character, rite=self.rite)

        self.assertFalse(result.success)
        self.assertIn("live scene", result.message)

    def test_unknown_rite_name_fails_softly(self) -> None:
        result = PerformWorshipRiteAction().run(actor=self.character, rite_name="nope")
        self.assertFalse(result.success)
