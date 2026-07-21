"""Tests for distinction removal and XP cost computation (#2607)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionFactory,
)
from world.distinctions.types import DistinctionChangeAction


class ComputeXPCostTests(TestCase):
    def test_add_positive_distinction(self):
        from world.distinctions.services import compute_distinction_change_xp_cost

        distinction = DistinctionFactory(cost_per_rank=10, max_rank=1)
        cost = compute_distinction_change_xp_cost(
            distinction, rank=1, action=DistinctionChangeAction.ADD
        )
        assert cost == 20  # 2 × 10 × 1

    def test_add_ranked_distinction(self):
        from world.distinctions.services import compute_distinction_change_xp_cost

        distinction = DistinctionFactory(cost_per_rank=5, max_rank=3)
        cost = compute_distinction_change_xp_cost(
            distinction, rank=3, action=DistinctionChangeAction.ADD
        )
        assert cost == 30  # 2 × 5 × 3

    def test_remove_positive_distinction_is_free(self):
        from world.distinctions.services import compute_distinction_change_xp_cost

        distinction = DistinctionFactory(cost_per_rank=10, max_rank=1)
        cost = compute_distinction_change_xp_cost(
            distinction, rank=1, action=DistinctionChangeAction.REMOVE
        )
        assert cost == 0  # losing a benefit for story reasons is free (#2631)

    def test_add_negative_distinction_is_free(self):
        from world.distinctions.services import compute_distinction_change_xp_cost

        distinction = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        cost = compute_distinction_change_xp_cost(
            distinction, rank=1, action=DistinctionChangeAction.ADD
        )
        assert cost == 0  # taking on a detriment is free (#2631)

    def test_add_rank_up_charges_delta_only(self):
        from world.distinctions.services import compute_distinction_change_xp_cost

        distinction = DistinctionFactory(cost_per_rank=5, max_rank=3)
        cost = compute_distinction_change_xp_cost(
            distinction, rank=3, action=DistinctionChangeAction.ADD, current_rank=2
        )
        assert cost == 10  # 2 × 5 × (3 − 2)

    def test_remove_negative_distinction_has_friction(self):
        from world.distinctions.services import compute_distinction_change_xp_cost

        distinction = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        cost = compute_distinction_change_xp_cost(
            distinction, rank=1, action=DistinctionChangeAction.REMOVE
        )
        assert cost == 150  # 2 × abs(-50) × 1 × 1.5


class RemoveDistinctionTests(TestCase):
    def test_remove_distinction_deletes_row(self):
        from world.distinctions.models import (
            CharacterDistinction,
            DistinctionChangeAuthorization,
        )
        from world.distinctions.services import remove_distinction

        sheet = CharacterSheetFactory()
        char_distinction = CharacterDistinctionFactory(character=sheet)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=sheet,
            action=DistinctionChangeAction.REMOVE,
            target_character_distinction=char_distinction,
            reason="Test removal",
            xp_cost=20,
        )
        remove_distinction(char_distinction, authorization=auth)
        assert not CharacterDistinction.objects.filter(pk=char_distinction.pk).exists()

    def test_remove_raises_on_consumed_authorization(self):
        from world.distinctions.exceptions import DistinctionAuthorizationError
        from world.distinctions.models import DistinctionChangeAuthorization
        from world.distinctions.services import remove_distinction

        sheet = CharacterSheetFactory()
        char_distinction = CharacterDistinctionFactory(character=sheet)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=sheet,
            action=DistinctionChangeAction.REMOVE,
            target_character_distinction=char_distinction,
            reason="Test",
            xp_cost=20,
            is_consumed=True,
        )
        with self.assertRaises(DistinctionAuthorizationError):
            remove_distinction(char_distinction, authorization=auth)

    def test_remove_raises_on_mismatched_target(self):
        from world.distinctions.exceptions import DistinctionAuthorizationError
        from world.distinctions.models import DistinctionChangeAuthorization
        from world.distinctions.services import remove_distinction

        sheet = CharacterSheetFactory()
        other_sheet = CharacterSheetFactory()
        char_distinction = CharacterDistinctionFactory(character=sheet)
        other_distinction = CharacterDistinctionFactory(character=other_sheet)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=other_sheet,
            action=DistinctionChangeAction.REMOVE,
            target_character_distinction=other_distinction,
            reason="Test",
            xp_cost=20,
        )
        with self.assertRaises(DistinctionAuthorizationError):
            remove_distinction(char_distinction, authorization=auth)


class SpendXPOnDistinctionUnlockTests(TestCase):
    def setUp(self):
        from unittest.mock import patch

        from evennia_extensions.factories import AccountFactory
        from world.progression.models.rewards import ExperiencePointsData

        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()
        self.xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=self.account,
            defaults={"total_earned": 100, "total_spent": 0},
        )
        self._patcher = patch("world.magic.services.alterations.enforce_advancement_gate")
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_spend_xp_for_removal(self):
        from world.distinctions.models import DistinctionChangeAuthorization
        from world.distinctions.services import spend_xp_on_distinction_unlock
        from world.progression.models.rewards import XPTransaction

        char_distinction = CharacterDistinctionFactory(character=self.sheet)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=self.sheet,
            action=DistinctionChangeAction.REMOVE,
            target_character_distinction=char_distinction,
            reason="Test",
            xp_cost=20,
        )
        spend_xp_on_distinction_unlock(self.sheet, auth)

        auth.refresh_from_db()
        assert auth.is_consumed
        assert auth.consumed_at is not None

        self.xp_tracker.refresh_from_db()
        assert self.xp_tracker.total_spent == 20

        txn = XPTransaction.objects.get(account=self.account, amount=-20)
        assert "Distinction change" in txn.description

    def test_spend_xp_raises_on_insufficient_xp(self):
        from world.distinctions.exceptions import DistinctionAuthorizationError
        from world.distinctions.models import DistinctionChangeAuthorization
        from world.distinctions.services import spend_xp_on_distinction_unlock

        self.xp_tracker.total_earned = 10
        self.xp_tracker.save()

        char_distinction = CharacterDistinctionFactory(character=self.sheet)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=self.sheet,
            action=DistinctionChangeAction.REMOVE,
            target_character_distinction=char_distinction,
            reason="Test",
            xp_cost=20,
        )
        with self.assertRaises(DistinctionAuthorizationError):
            spend_xp_on_distinction_unlock(self.sheet, auth)

    def test_spend_xp_raises_on_consumed_auth(self):
        from world.distinctions.exceptions import DistinctionAuthorizationError
        from world.distinctions.models import DistinctionChangeAuthorization
        from world.distinctions.services import spend_xp_on_distinction_unlock

        char_distinction = CharacterDistinctionFactory(character=self.sheet)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=self.sheet,
            action=DistinctionChangeAction.REMOVE,
            target_character_distinction=char_distinction,
            reason="Test",
            xp_cost=20,
            is_consumed=True,
        )
        with self.assertRaises(DistinctionAuthorizationError):
            spend_xp_on_distinction_unlock(self.sheet, auth)
