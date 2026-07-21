"""Tests for create_distinction_change_authorization + the #2631 Phase 0 repairs."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionFactory,
)
from world.distinctions.types import DistinctionChangeAction


class CreateChangeAuthorizationTests(TestCase):
    def test_add_stores_rank_and_computes_cost(self):
        from world.distinctions.services import create_distinction_change_authorization

        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=3)
        auth = create_distinction_change_authorization(
            sheet,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            authorized_by=None,
            reason="Story growth",
            rank=2,
        )
        assert auth.rank == 2
        assert auth.xp_cost == 20  # 2 × 5 × 2

    def test_rank_up_charges_delta_above_current(self):
        from world.distinctions.services import create_distinction_change_authorization

        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=3)
        CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=1)
        auth = create_distinction_change_authorization(
            sheet,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            authorized_by=None,
            reason="Story growth",
            rank=3,
        )
        assert auth.xp_cost == 20  # 2 × 5 × (3 − 1)

    def test_detriment_add_is_free(self):
        from world.distinctions.services import create_distinction_change_authorization

        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(cost_per_rank=-30, max_rank=1)
        auth = create_distinction_change_authorization(
            sheet,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            authorized_by=None,
            reason="Maimed in the siege",
        )
        assert auth.xp_cost == 0

    def test_explicit_zero_cost_override(self):
        from world.distinctions.services import create_distinction_change_authorization

        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(cost_per_rank=10, max_rank=1)
        auth = create_distinction_change_authorization(
            sheet,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            authorized_by=None,
            reason="GM waived the cost",
            xp_cost=0,
        )
        assert auth.xp_cost == 0

    def test_creation_notifies_the_player(self):
        from world.distinctions.services import create_distinction_change_authorization
        from world.narrative.models import NarrativeMessage

        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(cost_per_rank=10, max_rank=1)
        before = NarrativeMessage.objects.count()
        create_distinction_change_authorization(
            sheet,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            authorized_by=None,
            reason="Story growth",
        )
        assert NarrativeMessage.objects.count() == before + 1


class AcceptRankAndZeroCostTests(TestCase):
    def setUp(self):
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

    def test_accept_grants_the_authorized_rank(self):
        from world.distinctions.models import (
            CharacterDistinction,
            DistinctionChangeAuthorization,
        )
        from world.distinctions.services import spend_xp_on_distinction_unlock

        distinction = DistinctionFactory(cost_per_rank=5, max_rank=3)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=self.sheet,
            action=DistinctionChangeAction.ADD,
            target_distinction=distinction,
            rank=2,
            reason="Test",
            xp_cost=20,
        )
        spend_xp_on_distinction_unlock(self.sheet, auth)

        row = CharacterDistinction.objects.get(character=self.sheet, distinction=distinction)
        assert row.rank == 2

    def test_zero_cost_accept_writes_no_xp_transaction(self):
        from world.distinctions.models import DistinctionChangeAuthorization
        from world.distinctions.services import spend_xp_on_distinction_unlock
        from world.progression.models.rewards import XPTransaction

        distinction = DistinctionFactory(cost_per_rank=-30, max_rank=1)
        auth = DistinctionChangeAuthorization.objects.create(
            character_sheet=self.sheet,
            action=DistinctionChangeAction.ADD,
            target_distinction=distinction,
            rank=1,
            reason="Detriment for story reasons",
            xp_cost=0,
        )
        before = XPTransaction.objects.filter(account=self.account).count()
        spend_xp_on_distinction_unlock(self.sheet, auth)

        auth.refresh_from_db()
        assert auth.is_consumed
        assert XPTransaction.objects.filter(account=self.account).count() == before
        self.xp_tracker.refresh_from_db()
        assert self.xp_tracker.total_spent == 0
