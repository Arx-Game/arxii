"""Service tests for gift acquisition (#1587)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind
from world.magic.exceptions import XPInsufficient
from world.magic.factories import GiftFactory
from world.magic.models import GiftUnlock
from world.magic.services.gift_acquisition import (
    compute_gift_unlock_xp_cost,
    count_techniques_for_gift,
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
        CharacterPathHistoryFactory(character=self.sheet.character, path=path)
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
