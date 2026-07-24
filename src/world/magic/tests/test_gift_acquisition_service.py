"""Service tests for gift acquisition (#1587)."""

import itertools
from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind
from world.magic.exceptions import XPInsufficient
from world.magic.factories import GiftFactory
from world.magic.models import GiftUnlock, TechniqueTeachingOffer
from world.magic.services.gift_acquisition import (
    compute_gift_unlock_xp_cost,
    count_techniques_for_gift,
    get_gift_acquisition_config,
    get_technique_cap_for_gift,
    spend_xp_on_gift_unlock,
)


class ComputeGiftUnlockXpCostTest(TestCase):
    def setUp(self):
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.unlock = GiftUnlock.objects.create(gift=self.gift, xp_cost=10)
        self.sheet = CharacterSheetFactory()

    def test_path_neutral_unlock(self):
        # No paths set = available to all at base cost
        self.assertEqual(compute_gift_unlock_xp_cost(self.unlock, self.sheet), 10)

    def test_out_of_path_multiplier(self):
        from world.classes.factories import PathFactory

        path = PathFactory()
        self.unlock.paths.add(path)
        # Learner has no path history with this path
        cost = compute_gift_unlock_xp_cost(self.unlock, self.sheet)
        self.assertEqual(cost, 20)  # 10 * 2.0

    def test_in_path(self):
        from world.classes.factories import PathFactory
        from world.progression.factories import CharacterPathHistoryFactory

        path = PathFactory()
        self.unlock.paths.add(path)
        CharacterPathHistoryFactory(character=self.sheet, path=path)
        cost = compute_gift_unlock_xp_cost(self.unlock, self.sheet)
        self.assertEqual(cost, 10)  # in-Path, base cost


class SpendXpOnGiftUnlockTest(TestCase):
    def setUp(self):
        from evennia_extensions.factories import AccountFactory
        from world.progression.models.rewards import ExperiencePointsData

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.unlock = GiftUnlock.objects.create(gift=self.gift, xp_cost=10)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()
        self.xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=self.account,
            defaults={"total_earned": 100, "total_spent": 0},
        )

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_successful_spend(self, mock_gate):
        mock_gate.return_value = None
        receipt = spend_xp_on_gift_unlock(self.sheet, self.unlock)
        self.assertEqual(receipt.xp_spent, 10)
        self.assertEqual(receipt.character, self.sheet)
        self.assertEqual(receipt.unlock, self.unlock)
        self.xp_tracker.refresh_from_db()
        self.assertEqual(self.xp_tracker.total_spent, 10)

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_insufficient_xp(self, mock_gate):
        mock_gate.return_value = None
        self.xp_tracker.total_earned = 5
        self.xp_tracker.total_spent = 0
        self.xp_tracker.save()
        with self.assertRaises(XPInsufficient):
            spend_xp_on_gift_unlock(self.sheet, self.unlock)

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_duplicate_unlock_raises_integrity(self, mock_gate):
        from django.db import IntegrityError

        mock_gate.return_value = None
        spend_xp_on_gift_unlock(self.sheet, self.unlock)
        with self.assertRaises(IntegrityError):
            spend_xp_on_gift_unlock(self.sheet, self.unlock)


class TechniqueCapTest(TestCase):
    def setUp(self):
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.sheet = CharacterSheetFactory()

    def test_count_zero_when_no_techniques(self):
        self.assertEqual(count_techniques_for_gift(self.sheet, self.gift), 0)

    def test_cap_zero_when_no_thread(self):
        # No GIFT thread -> depth 0 -> cap 0
        self.assertEqual(get_technique_cap_for_gift(self.sheet, self.gift), 0)

    def test_cap_with_level_0_thread(self):
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Thread

        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )
        # depth = max(1, 0 // 10) = max(1, 0) = 1, cap = 3 * 1 = 3
        self.assertEqual(get_technique_cap_for_gift(self.sheet, self.gift), 3)

    def test_cap_with_level_10_thread(self):
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Thread

        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )
        # depth = max(1, 10 // 10) = 1, cap = 3 * 1 = 3
        self.assertEqual(get_technique_cap_for_gift(self.sheet, self.gift), 3)

    def test_cap_with_level_25_thread(self):
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Thread

        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=25,
        )
        # depth = max(1, 25 // 10) = 2, cap = 3 * 2 = 6
        self.assertEqual(get_technique_cap_for_gift(self.sheet, self.gift), 6)

    def test_cap_never_drops_to_zero_for_levels_1_through_9(self):
        """Regression (#1718 final-review Finding 1).

        thread_level_multiplier(level) ramps linearly 0.1..0.9 across levels
        1-9 for continuous combat-scaling use; round()'d naively that lands on
        0 for levels 1-5, which would drop the technique cap to 0 for a
        character who just advanced a Gift thread off level 0 — strictly
        worse than owning no thread progress at all. Depth must stay >= 1 for
        every level >= 1.
        """
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Thread

        resonance = ResonanceFactory()
        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=1,
        )
        for level in range(1, 10):
            thread.level = level
            thread.save()
            cap = get_technique_cap_for_gift(self.sheet, self.gift)
            self.assertGreaterEqual(
                cap,
                3,
                f"cap dropped below the level-1 floor at thread level {level}",
            )

    def test_cap_monotonically_non_decreasing_across_levels_0_to_10(self):
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Thread

        resonance = ResonanceFactory()
        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )
        caps = []
        for level in range(11):
            thread.level = level
            thread.save()
            caps.append(get_technique_cap_for_gift(self.sheet, self.gift))
        for earlier, later in itertools.pairwise(caps):
            self.assertLessEqual(earlier, later, f"caps regressed across levels: {caps}")


class AcceptTechniqueOfferTest(TestCase):
    def setUp(self):
        from evennia_extensions.factories import AccountFactory
        from world.action_points.models import ActionPointPool
        from world.magic.factories import ResonanceFactory, TechniqueFactory
        from world.progression.models.rewards import ExperiencePointsData
        from world.roster.factories import RosterTenureFactory

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)
        self.technique = TechniqueFactory(gift=self.gift)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()
        self.teacher_tenure = RosterTenureFactory()
        self.unlock = GiftUnlock.objects.create(gift=self.gift, xp_cost=10)

        self.xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=self.account,
            defaults={"total_earned": 100, "total_spent": 0},
        )
        self.learner_ap = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.learner_ap.current = 200
        self.learner_ap.save()
        self.teacher_ap = ActionPointPool.get_or_create_for_character(self.teacher_tenure.character)
        self.teacher_ap.current = 200
        self.teacher_ap.save()

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_first_technique_acquires_gift(self, mock_gate):
        mock_gate.return_value = None
        spend_xp_on_gift_unlock(self.sheet, self.unlock)

        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique,
            pitch="I teach you",
            learn_ap_cost=5,
            banked_ap=1,
        )

        from world.magic.services.gift_acquisition import accept_technique_offer

        ct = accept_technique_offer(self.sheet, offer)
        self.assertEqual(ct.character, self.sheet)
        self.assertEqual(ct.technique, self.technique)

        # Gift was implicitly acquired
        from world.magic.models import CharacterGift

        self.assertTrue(CharacterGift.objects.filter(character=self.sheet, gift=self.gift).exists())

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_first_technique_without_unlock_raises(self, mock_gate):
        mock_gate.return_value = None
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique,
            pitch="I teach you",
            learn_ap_cost=5,
            banked_ap=1,
        )

        from world.magic.exceptions import GiftUnlockMissing
        from world.magic.services.gift_acquisition import accept_technique_offer

        with self.assertRaises(GiftUnlockMissing):
            accept_technique_offer(self.sheet, offer)

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_first_technique_costs_more_ap(self, mock_gate):
        mock_gate.return_value = None
        spend_xp_on_gift_unlock(self.sheet, self.unlock)

        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique,
            pitch="I teach you",
            learn_ap_cost=5,
            banked_ap=1,
        )

        from world.magic.services.gift_acquisition import accept_technique_offer

        accept_technique_offer(self.sheet, offer)
        self.learner_ap.refresh_from_db()
        # 5 * 3 (first_technique_ap_multiplier) = 15 AP
        self.assertEqual(self.learner_ap.current, 200 - 15)

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_second_technique_costs_base_ap(self, mock_gate):
        mock_gate.return_value = None
        spend_xp_on_gift_unlock(self.sheet, self.unlock)

        from world.magic.factories import TechniqueFactory
        from world.magic.services.gift_acquisition import accept_technique_offer

        tech1 = TechniqueFactory(gift=self.gift)
        offer1 = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=tech1,
            pitch="first",
            learn_ap_cost=5,
            banked_ap=1,
        )
        accept_technique_offer(self.sheet, offer1)

        # Second technique (gift already owned — base AP, no multiplier)
        tech2 = TechniqueFactory(gift=self.gift)
        offer2 = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=tech2,
            pitch="second",
            learn_ap_cost=5,
            banked_ap=1,
        )
        self.learner_ap.current = 200
        self.learner_ap.save()
        accept_technique_offer(self.sheet, offer2)
        self.learner_ap.refresh_from_db()
        # 5 AP (no multiplier, gift already owned)
        self.assertEqual(self.learner_ap.current, 200 - 5)

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_major_gift_subsequent_technique_uses_multiplier(self, mock_gate):
        """Major-gift techniques use major_gift_ap_multiplier on the has_gift branch."""
        from world.magic.constants import GiftKind
        from world.magic.factories import TechniqueFactory
        from world.magic.models import CharacterGift
        from world.magic.services.gift_acquisition import accept_technique_offer

        mock_gate.return_value = None
        major_gift = GiftFactory(kind=GiftKind.MAJOR)
        major_gift.resonances.add(self.resonance)
        # Give the character the major gift (simulating CG ownership)
        CharacterGift.objects.create(character=self.sheet, gift=major_gift)
        # Provision a GIFT thread so the technique cap is > 0
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=major_gift,
            level=0,
        )

        config = get_gift_acquisition_config()
        config.major_gift_ap_multiplier = 2
        config.save()

        tech = TechniqueFactory(gift=major_gift)
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=tech,
            pitch="major gift tech",
            learn_ap_cost=5,
            banked_ap=1,
        )
        self.learner_ap.current = 200
        self.learner_ap.save()
        accept_technique_offer(self.sheet, offer)
        self.learner_ap.refresh_from_db()
        # 5 * 2 (major_gift_ap_multiplier) = 10 AP
        self.assertEqual(self.learner_ap.current, 200 - 10)

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_path_style_forbidden_blocks_accept(self, mock_gate):
        """accept_technique_offer raises TechniqueStyleForbidden on path mismatch."""
        from world.classes.factories import PathFactory
        from world.magic.exceptions import TechniqueStyleForbidden
        from world.magic.factories import TechniqueStyleFactory
        from world.progression.factories import CharacterPathHistoryFactory

        mock_gate.return_value = None
        allowed_path = PathFactory()
        other_path = PathFactory()
        CharacterPathHistoryFactory(character=self.sheet, path=other_path)
        style = TechniqueStyleFactory(allowed_paths=[allowed_path])
        from world.magic.factories import TechniqueFactory
        from world.magic.services.gift_acquisition import accept_technique_offer

        forbidden_tech = TechniqueFactory(gift=self.gift, style=style)

        spend_xp_on_gift_unlock(self.sheet, self.unlock)
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=forbidden_tech,
            pitch="forbidden",
            learn_ap_cost=5,
            banked_ap=1,
        )
        with self.assertRaises(TechniqueStyleForbidden):
            accept_technique_offer(self.sheet, offer)

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_technique_cap_exceeded(self, mock_gate):
        mock_gate.return_value = None
        spend_xp_on_gift_unlock(self.sheet, self.unlock)

        from world.magic.constants import TargetKind
        from world.magic.exceptions import TechniqueCapExceeded
        from world.magic.factories import ResonanceFactory, TechniqueFactory
        from world.magic.models import Thread
        from world.magic.services.gift_acquisition import accept_technique_offer

        # Provision a level-10 GIFT thread (depth 1, cap 3)
        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )

        # Learn 3 techniques (fills the cap)
        for _ in range(3):
            tech = TechniqueFactory(gift=self.gift)
            offer = TechniqueTeachingOffer.objects.create(
                teacher=self.teacher_tenure,
                technique=tech,
                pitch="filling",
                learn_ap_cost=5,
                banked_ap=1,
            )
            self.learner_ap.current = 200
            self.learner_ap.save()
            accept_technique_offer(self.sheet, offer)

        # 4th should fail
        tech4 = TechniqueFactory(gift=self.gift)
        offer4 = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=tech4,
            pitch="over cap",
            learn_ap_cost=5,
            banked_ap=1,
        )
        with self.assertRaises(TechniqueCapExceeded):
            accept_technique_offer(self.sheet, offer4)


class ChargeAndLearnGoldCostTest(TestCase):
    """The shared core's gold-charge branch (#2440) — no player-teacher offer

    exercises ``gold_cost``/``gold_treasury`` today (TechniqueTeachingOffer's
    own gold_cost field is still unwired), so this is covered directly here
    rather than only indirectly through the npc_services TRAIN offer tests.
    """

    def setUp(self):
        from evennia_extensions.factories import AccountFactory
        from world.action_points.models import ActionPointPool
        from world.currency.services import get_or_create_purse, get_or_create_treasury
        from world.magic.constants import TargetKind
        from world.magic.factories import (
            CharacterGiftFactory,
            ResonanceFactory,
            TechniqueFactory,
        )
        from world.magic.models import Thread
        from world.societies.factories import OrganizationFactory

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()
        # Already-owned gift + provisioned thread — sidesteps the XP-unlock
        # gate and the technique cap so this test stays focused on gold.
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )
        self.technique = TechniqueFactory(gift=self.gift)
        self.ap_pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.ap_pool.current = 200
        self.ap_pool.save()
        self.purse = get_or_create_purse(self.sheet)
        self.purse.balance = 1000
        self.purse.save()
        self.org = OrganizationFactory()
        self.treasury = get_or_create_treasury(self.org)

    def test_gold_cost_transfers_purse_to_treasury(self):
        from world.achievements.constants import AccessChangeSource
        from world.magic.services.gift_acquisition import charge_and_learn

        ct = charge_and_learn(
            self.sheet,
            self.technique,
            base_ap_cost=5,
            source=AccessChangeSource.ACADEMY_TRAINING,
            gold_cost=100,
            gold_treasury=self.treasury,
        )
        self.assertEqual(ct.technique, self.technique)
        self.purse.refresh_from_db()
        self.treasury.refresh_from_db()
        self.assertEqual(self.purse.balance, 900)
        self.assertEqual(self.treasury.balance, 100)

    def test_zero_gold_cost_does_not_touch_purse(self):
        from world.achievements.constants import AccessChangeSource
        from world.magic.services.gift_acquisition import charge_and_learn

        charge_and_learn(
            self.sheet,
            self.technique,
            base_ap_cost=5,
            source=AccessChangeSource.ACADEMY_TRAINING,
        )
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 1000)


class UnboundMagicLearningApSurchargeTest(TestCase):
    """The Unbound magic-learning AP surcharge (#2442) on the PC-teaching-accept
    door (``accept_technique_offer``). TIME, not power — resonance is untouched;
    only the AP charged at the shared ``charge_and_learn`` seam scales."""

    def setUp(self):
        from evennia_extensions.factories import AccountFactory
        from world.action_points.models import ActionPointPool
        from world.magic.constants import TargetKind
        from world.magic.factories import CharacterGiftFactory, ResonanceFactory
        from world.magic.models import Thread
        from world.roster.factories import RosterTenureFactory
        from world.seeds.character_creation import ensure_unbound_drawback_distinction

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()
        # Already-owned gift + provisioned thread — sidesteps the XP-unlock gate
        # and the technique cap so these tests stay focused on the surcharge.
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )
        self.teacher_tenure = RosterTenureFactory()
        self.learner_ap = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.learner_ap.current = 200
        self.learner_ap.save()
        self.teacher_ap = ActionPointPool.get_or_create_for_character(self.teacher_tenure.character)
        self.teacher_ap.current = 200
        self.teacher_ap.save()
        self.unbound_distinction = ensure_unbound_drawback_distinction()

    def _grant_unbound(self):
        from world.distinctions.services import grant_distinction
        from world.distinctions.types import DistinctionOrigin

        grant_distinction(
            self.sheet,
            self.unbound_distinction,
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )

    def test_unbound_learner_pays_surcharge(self):
        from world.magic.factories import TechniqueFactory
        from world.magic.services.gift_acquisition import accept_technique_offer

        self._grant_unbound()
        technique = TechniqueFactory(gift=self.gift)
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=technique,
            pitch="Unbound, but eager to learn",
            learn_ap_cost=5,
            banked_ap=1,
        )

        ct = accept_technique_offer(self.sheet, offer)

        self.assertEqual(ct.technique, technique)
        self.learner_ap.refresh_from_db()
        # Gift already owned (MINOR) -> base AP 5, then ceil(5 * 1.5) = 8.
        self.assertEqual(self.learner_ap.current, 200 - 8)

    def test_non_unbound_learner_unaffected(self):
        from world.magic.factories import TechniqueFactory
        from world.magic.services.gift_acquisition import accept_technique_offer

        technique = TechniqueFactory(gift=self.gift)
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=technique,
            pitch="Trained and true",
            learn_ap_cost=5,
            banked_ap=1,
        )

        accept_technique_offer(self.sheet, offer)

        self.learner_ap.refresh_from_db()
        self.assertEqual(self.learner_ap.current, 200 - 5)

    def test_surcharge_reapplies_after_leaving_a_living_tradition(self):
        """Mirror of ``test_surcharge_disappears_after_joining_a_living_tradition``
        (review-requested, Minor): a member of a living tradition pays base AP;
        ``leave_tradition`` re-applies the REAL seeded "unbound" drawback
        (``ensure_unbound_drawback_distinction`` in ``setUp``, #2441 ruling 4 / #2442
        Task 9), and the very next acquisition is charged the surcharge again."""
        from world.magic.factories import TechniqueFactory, TraditionFactory
        from world.magic.services.gift_acquisition import accept_technique_offer
        from world.magic.services.tradition_membership import join_tradition, leave_tradition

        tradition = TraditionFactory(name="The Caretakers")
        join_tradition(self.sheet, tradition)

        technique_before = TechniqueFactory(gift=self.gift)
        offer_before = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=technique_before,
            pitch="Trained and true",
            learn_ap_cost=5,
            banked_ap=1,
        )
        accept_technique_offer(self.sheet, offer_before)
        self.learner_ap.refresh_from_db()
        self.assertEqual(self.learner_ap.current, 200 - 5)

        leave_tradition(self.sheet)

        technique_after = TechniqueFactory(gift=self.gift)
        offer_after = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=technique_after,
            pitch="Traditionless once more",
            learn_ap_cost=5,
            banked_ap=1,
        )
        accept_technique_offer(self.sheet, offer_after)

        self.learner_ap.refresh_from_db()
        # base AP (5) already spent above; this second charge is ceil(5 * 1.5) = 8.
        self.assertEqual(self.learner_ap.current, 200 - 5 - 8)

    def test_surcharge_disappears_after_joining_a_living_tradition(self):
        """Integration with #2441 Task 8 — join_tradition sheds the Unbound
        drawback; its ModifierSource/CharacterModifier rows cascade-delete
        (ModifierSource.character_distinction is CASCADE), so the next
        acquisition is charged at the un-surcharged rate."""
        from world.magic.factories import TechniqueFactory, TraditionFactory
        from world.magic.services.gift_acquisition import accept_technique_offer
        from world.magic.services.tradition_membership import join_tradition

        self._grant_unbound()
        join_tradition(self.sheet, TraditionFactory(name="The Caretakers"))

        technique = TechniqueFactory(gift=self.gift)
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=technique,
            pitch="No longer Unbound",
            learn_ap_cost=5,
            banked_ap=1,
        )

        accept_technique_offer(self.sheet, offer)

        self.learner_ap.refresh_from_db()
        self.assertEqual(self.learner_ap.current, 200 - 5)
