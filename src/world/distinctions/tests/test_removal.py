"""Tests for distinction removal and XP cost computation (#2607)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionFactory,
)
from world.distinctions.types import (
    DistinctionOrigin,
    SheetUpdateRequestStatus,
    SheetUpdateRequestType,
)


class ComputeXPCostTests(TestCase):
    def test_add_positive_distinction(self):
        from world.distinctions.services import compute_sheet_update_xp_cost

        distinction = DistinctionFactory(cost_per_rank=10, max_rank=1)
        cost = compute_sheet_update_xp_cost(
            SheetUpdateRequestType.DISTINCTION_ADD, distinction, rank=1
        )
        assert cost == 10  # abs(10) * 1

    def test_add_ranked_distinction(self):
        from world.distinctions.services import compute_sheet_update_xp_cost

        distinction = DistinctionFactory(cost_per_rank=5, max_rank=3)
        cost = compute_sheet_update_xp_cost(
            SheetUpdateRequestType.DISTINCTION_ADD, distinction, rank=3
        )
        assert cost == 15  # abs(5) * 3

    def test_add_negative_distinction_is_free(self):
        from world.distinctions.services import compute_sheet_update_xp_cost

        distinction = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        cost = compute_sheet_update_xp_cost(
            SheetUpdateRequestType.DISTINCTION_ADD, distinction, rank=1
        )
        assert cost == 0  # negative distinction: free to add

    def test_remove_positive_distinction_is_free(self):
        from world.distinctions.services import compute_sheet_update_xp_cost

        distinction = DistinctionFactory(cost_per_rank=10, max_rank=1)
        cost = compute_sheet_update_xp_cost(
            SheetUpdateRequestType.DISTINCTION_REMOVE, distinction, rank=1
        )
        assert cost == 0  # positive distinction: free to remove

    def test_remove_negative_distinction_costs_xp(self):
        from world.distinctions.services import compute_sheet_update_xp_cost

        distinction = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        cost = compute_sheet_update_xp_cost(
            SheetUpdateRequestType.DISTINCTION_REMOVE, distinction, rank=1
        )
        assert cost == 50  # abs(-50) * 1 — no friction multiplier


class RemoveDistinctionTests(TestCase):
    def test_remove_distinction_deletes_row(self):
        from world.distinctions.models import (
            CharacterDistinction,
            SheetUpdateRequest,
        )
        from world.distinctions.services import remove_distinction

        sheet = CharacterSheetFactory()
        char_distinction = CharacterDistinctionFactory(character=sheet)
        req = SheetUpdateRequest.objects.create(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_REMOVE,
            target_character_distinction=char_distinction,
            justification="Test removal",
            xp_cost=0,
            status=SheetUpdateRequestStatus.APPROVED,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        remove_distinction(char_distinction, sheet_update_request=req)
        assert not CharacterDistinction.objects.filter(pk=char_distinction.pk).exists()

    def test_remove_raises_on_non_approved_request(self):
        from world.distinctions.exceptions import SheetUpdateRequestError
        from world.distinctions.models import SheetUpdateRequest
        from world.distinctions.services import remove_distinction

        sheet = CharacterSheetFactory()
        char_distinction = CharacterDistinctionFactory(character=sheet)
        req = SheetUpdateRequest.objects.create(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_REMOVE,
            target_character_distinction=char_distinction,
            justification="Test",
            xp_cost=0,
            status=SheetUpdateRequestStatus.DENIED,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(SheetUpdateRequestError):
            remove_distinction(char_distinction, sheet_update_request=req)

    def test_remove_raises_on_mismatched_target(self):
        from world.distinctions.exceptions import SheetUpdateRequestError
        from world.distinctions.models import SheetUpdateRequest
        from world.distinctions.services import remove_distinction

        sheet = CharacterSheetFactory()
        other_sheet = CharacterSheetFactory()
        char_distinction = CharacterDistinctionFactory(character=sheet)
        other_distinction = CharacterDistinctionFactory(character=other_sheet)
        req = SheetUpdateRequest.objects.create(
            character_sheet=other_sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_REMOVE,
            target_character_distinction=other_distinction,
            justification="Test",
            xp_cost=0,
            status=SheetUpdateRequestStatus.APPROVED,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(SheetUpdateRequestError):
            remove_distinction(char_distinction, sheet_update_request=req)


class CreateSheetUpdateRequestTests(TestCase):
    def test_create_add_request_stamps_xp_cost(self):
        from world.distinctions.services import create_sheet_update_request

        sheet = CharacterSheetFactory()
        dist = DistinctionFactory(cost_per_rank=10, max_rank=1)
        req = create_sheet_update_request(
            sheet,
            SheetUpdateRequestType.DISTINCTION_ADD,
            justification="Story reason",
            target_distinction=dist,
        )
        assert req.xp_cost == 10
        assert req.status == SheetUpdateRequestStatus.PENDING

    def test_create_add_negative_distinction_is_free(self):
        from world.distinctions.services import create_sheet_update_request

        sheet = CharacterSheetFactory()
        dist = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        req = create_sheet_update_request(
            sheet,
            SheetUpdateRequestType.DISTINCTION_ADD,
            justification="Story reason",
            target_distinction=dist,
        )
        assert req.xp_cost == 0

    def test_create_remove_request_stamps_xp_cost(self):
        from world.distinctions.services import create_sheet_update_request

        sheet = CharacterSheetFactory()
        dist = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        cd = CharacterDistinctionFactory(character=sheet, distinction=dist, rank=1)
        req = create_sheet_update_request(
            sheet,
            SheetUpdateRequestType.DISTINCTION_REMOVE,
            justification="Story reason",
            target_character_distinction=cd,
        )
        assert req.xp_cost == 50  # abs(-50) * 1


class ApproveSheetUpdateRequestTests(TestCase):
    def setUp(self):
        from unittest.mock import patch

        from evennia_extensions.factories import AccountFactory
        from world.progression.models.rewards import ExperiencePointsData

        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()
        self.gm_account = AccountFactory()
        self.xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=self.account,
            defaults={"total_earned": 100, "total_spent": 0},
        )
        self._patcher = patch("world.magic.services.alterations.enforce_advancement_gate")
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_approve_add_grants_distinction_and_debits_xp(self):
        from world.distinctions.models import CharacterDistinction, SheetUpdateRequest
        from world.distinctions.services import approve_sheet_update_request
        from world.progression.models.rewards import XPTransaction

        dist = DistinctionFactory(cost_per_rank=10, max_rank=1)
        req = SheetUpdateRequest.objects.create(
            character_sheet=self.sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            justification="Test",
            xp_cost=10,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        approve_sheet_update_request(req, self.gm_account)

        req.refresh_from_db()
        assert req.status == SheetUpdateRequestStatus.APPROVED
        assert req.reviewed_by == self.gm_account
        assert req.reviewed_at is not None

        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=dist)
        assert cd.origin == DistinctionOrigin.UNLOCK_PURCHASE

        self.xp_tracker.refresh_from_db()
        assert self.xp_tracker.total_spent == 10

        txn = XPTransaction.objects.get(account=self.account, amount=-10)
        assert "Distinction" in txn.description

    def test_approve_remove_deletes_distinction_and_debits_xp(self):
        from world.distinctions.models import (
            CharacterDistinction,
            SheetUpdateRequest,
        )
        from world.distinctions.services import approve_sheet_update_request

        dist = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        cd = CharacterDistinctionFactory(character=self.sheet, distinction=dist, rank=1)
        req = SheetUpdateRequest.objects.create(
            character_sheet=self.sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_REMOVE,
            target_character_distinction=cd,
            justification="Test",
            xp_cost=50,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        approve_sheet_update_request(req, self.gm_account)

        req.refresh_from_db()
        assert req.status == SheetUpdateRequestStatus.APPROVED
        assert not CharacterDistinction.objects.filter(pk=cd.pk).exists()

        self.xp_tracker.refresh_from_db()
        assert self.xp_tracker.total_spent == 50

    def test_approve_free_transaction_does_not_debit_xp(self):
        from world.distinctions.models import CharacterDistinction, SheetUpdateRequest
        from world.distinctions.services import approve_sheet_update_request

        dist = DistinctionFactory(cost_per_rank=-10, max_rank=1)  # free to add
        req = SheetUpdateRequest.objects.create(
            character_sheet=self.sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            justification="Test",
            xp_cost=0,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        approve_sheet_update_request(req, self.gm_account)

        self.xp_tracker.refresh_from_db()
        assert self.xp_tracker.total_spent == 0
        assert CharacterDistinction.objects.filter(character=self.sheet, distinction=dist).exists()

    def test_approve_fails_on_insufficient_xp(self):
        from world.distinctions.exceptions import SheetUpdateRequestError
        from world.distinctions.models import SheetUpdateRequest
        from world.distinctions.services import approve_sheet_update_request

        self.xp_tracker.total_earned = 5
        self.xp_tracker.save()

        dist = DistinctionFactory(cost_per_rank=10, max_rank=1)
        req = SheetUpdateRequest.objects.create(
            character_sheet=self.sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            justification="Test",
            xp_cost=10,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(SheetUpdateRequestError):
            approve_sheet_update_request(req, self.gm_account)

        req.refresh_from_db()
        assert req.status == SheetUpdateRequestStatus.PENDING  # unchanged

    def test_approve_fails_on_already_processed(self):
        from world.distinctions.exceptions import SheetUpdateRequestError
        from world.distinctions.models import SheetUpdateRequest
        from world.distinctions.services import approve_sheet_update_request

        dist = DistinctionFactory(cost_per_rank=10, max_rank=1)
        req = SheetUpdateRequest.objects.create(
            character_sheet=self.sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            justification="Test",
            xp_cost=10,
            status=SheetUpdateRequestStatus.APPROVED,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(SheetUpdateRequestError):
            approve_sheet_update_request(req, self.gm_account)


class DenySheetUpdateRequestTests(TestCase):
    def test_deny_sets_status_and_no_change(self):
        from world.distinctions.models import (
            CharacterDistinction,
            SheetUpdateRequest,
        )
        from world.distinctions.services import deny_sheet_update_request

        sheet = CharacterSheetFactory()
        dist = DistinctionFactory(cost_per_rank=10, max_rank=1)
        req = SheetUpdateRequest.objects.create(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            justification="Test",
            xp_cost=10,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        from evennia_extensions.factories import AccountFactory

        gm_account = AccountFactory()

        deny_sheet_update_request(req, gm_account)

        req.refresh_from_db()
        assert req.status == SheetUpdateRequestStatus.DENIED
        assert req.reviewed_by == gm_account
        assert not CharacterDistinction.objects.filter(character=sheet, distinction=dist).exists()


class CancelSheetUpdateRequestTests(TestCase):
    def test_cancel_deletes_pending_request(self):
        from world.distinctions.models import SheetUpdateRequest
        from world.distinctions.services import cancel_sheet_update_request

        sheet = CharacterSheetFactory()
        from evennia_extensions.factories import AccountFactory

        account = AccountFactory()
        sheet.character.account = account
        sheet.character.save()
        dist = DistinctionFactory(cost_per_rank=10, max_rank=1)
        req = SheetUpdateRequest.objects.create(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            justification="Test",
            xp_cost=10,
            submitted_by=account,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        cancel_sheet_update_request(req, account)
        assert not SheetUpdateRequest.objects.filter(pk=req.pk).exists()

    def test_cancel_rejects_non_pending(self):
        from world.distinctions.exceptions import SheetUpdateRequestError
        from world.distinctions.models import SheetUpdateRequest
        from world.distinctions.services import cancel_sheet_update_request

        sheet = CharacterSheetFactory()
        from evennia_extensions.factories import AccountFactory

        account = AccountFactory()
        sheet.character.account = account
        sheet.character.save()
        dist = DistinctionFactory(cost_per_rank=10, max_rank=1)
        req = SheetUpdateRequest.objects.create(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            justification="Test",
            xp_cost=10,
            status=SheetUpdateRequestStatus.APPROVED,
            submitted_by=account,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(SheetUpdateRequestError):
            cancel_sheet_update_request(req, account)
