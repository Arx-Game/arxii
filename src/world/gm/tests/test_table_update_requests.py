"""Tests for the TableUpdateRequest framework (#2631, on the #2628 engine)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.models import ProfileTextVersion
from world.character_sheets.types import ProfileTextField
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionFactory,
)
from world.distinctions.types import SheetUpdateRequestStatus, SheetUpdateRequestType
from world.gm.constants import TableRequestKind, TableRequestStatus
from world.gm.factories import (
    GMProfileFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.gm.services import (
    TableRequestError,
    gm_may_review_for_persona,
    signoff_table_update_request,
    submit_distinction_change_request,
    submit_profile_text_request,
    withdraw_table_update_request,
)


def _fund_sheet(sheet, total_earned=100):
    """Attach an account with XP to the sheet's character."""
    from world.progression.models.rewards import ExperiencePointsData

    account = AccountFactory()
    sheet.character.db_account = account
    sheet.character.save()
    ExperiencePointsData.objects.get_or_create(
        account=account,
        defaults={"total_earned": total_earned, "total_spent": 0},
    )
    return account


class SubmitRequestTests(TestCase):
    def setUp(self):
        self.membership = GMTableMembershipFactory()
        self.sheet = self.membership.persona.character_sheet

    def test_submit_profile_text_request(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="A new chapter.",
            reasoning="The siege changed everything.",
        )
        assert request.status == TableRequestStatus.PENDING
        assert request.kind == TableRequestKind.PROFILE_TEXT
        assert request.profile_text_details.proposed_text == "A new chapter."

    def test_submit_rejects_unknown_field(self):
        with self.assertRaises(TableRequestError):
            submit_profile_text_request(
                self.membership,
                field="obituary",
                proposed_text="text",
                reasoning="reason",
            )

    def test_submit_rejects_left_membership(self):
        self.membership.left_at = timezone.now()
        self.membership.save()
        with self.assertRaises(TableRequestError):
            submit_profile_text_request(
                self.membership,
                field=ProfileTextField.BACKGROUND,
                proposed_text="text",
                reasoning="reason",
            )

    def test_submit_distinction_change_request(self):
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=1)
        request = submit_distinction_change_request(
            self.membership,
            action=SheetUpdateRequestType.DISTINCTION_ADD,
            distinction=distinction,
            reasoning="Earned it in the story.",
        )
        assert request.kind == TableRequestKind.DISTINCTION_CHANGE
        assert request.distinction_details.distinction == distinction

    def test_submit_rejects_other_characters_distinction(self):
        other = CharacterDistinctionFactory()  # different sheet
        with self.assertRaises(TableRequestError):
            submit_distinction_change_request(
                self.membership,
                action=SheetUpdateRequestType.DISTINCTION_REMOVE,
                character_distinction=other,
                reasoning="reason",
            )


class ReviewPoolTests(TestCase):
    """The #2631 ruling: staff or any GM whose table the persona sits at."""

    def setUp(self):
        self.membership = GMTableMembershipFactory()
        self.persona = self.membership.persona

    def test_own_table_gm_may_review(self):
        assert gm_may_review_for_persona(self.membership.table.gm, self.persona)

    def test_other_table_gm_of_same_persona_may_review(self):
        other_table = GMTableFactory()
        GMTableMembershipFactory(table=other_table, persona=self.persona)
        assert gm_may_review_for_persona(other_table.gm, self.persona)

    def test_stranger_gm_may_not_review(self):
        stranger = GMProfileFactory()
        assert not gm_may_review_for_persona(stranger, self.persona)

    def test_stranger_gm_signoff_raises(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        with self.assertRaises(TableRequestError):
            signoff_table_update_request(request, GMProfileFactory(), approve=True)


class SignoffTests(TestCase):
    def setUp(self):
        self.membership = GMTableMembershipFactory()
        self.gm = self.membership.table.gm
        self.sheet = self.membership.persona.character_sheet
        self._patcher = patch("world.magic.services.alterations.enforce_advancement_gate")
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_approve_profile_text_applies_and_completes(self):
        profile = self.sheet.true_profile
        profile.background = "The old story."
        profile.save(update_fields=["background"])

        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="The new story.",
            reasoning="Growth.",
        )
        signoff_table_update_request(request, self.gm, approve=True, notes="Fits the arc.")

        request.refresh_from_db()
        assert request.status == TableRequestStatus.COMPLETED
        assert request.completed_at is not None
        profile.refresh_from_db()
        assert profile.background == "The new story."
        versions = ProfileTextVersion.objects.filter(
            profile=profile, field=ProfileTextField.BACKGROUND
        ).order_by("created_at")
        assert [v.text for v in versions] == ["The old story.", "The new story."]
        assert request.profile_text_details.applied_version == versions.last()

    def test_approve_distinction_debits_xp_and_grants(self):
        from world.distinctions.models import CharacterDistinction
        from world.progression.models.rewards import ExperiencePointsData

        account = _fund_sheet(self.sheet, total_earned=100)
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=2)
        request = submit_distinction_change_request(
            self.membership,
            action=SheetUpdateRequestType.DISTINCTION_ADD,
            distinction=distinction,
            reasoning="Earned it.",
        )
        signoff_table_update_request(request, self.gm, approve=True)

        request.refresh_from_db()
        assert request.status == TableRequestStatus.COMPLETED
        sheet_request = request.distinction_details.sheet_update_request
        assert sheet_request is not None
        sheet_request.refresh_from_db()
        assert sheet_request.status == SheetUpdateRequestStatus.APPROVED
        assert sheet_request.xp_cost == 5  # |cost_per_rank| × 1, sign-based (#2628)
        row = CharacterDistinction.objects.get(character=self.sheet, distinction=distinction)
        assert row.rank == 1
        tracker = ExperiencePointsData.objects.get(account=account)
        assert tracker.total_spent == 5

    def test_approve_distinction_insufficient_xp_stays_pending(self):
        _fund_sheet(self.sheet, total_earned=1)
        distinction = DistinctionFactory(cost_per_rank=50, max_rank=1)
        request = submit_distinction_change_request(
            self.membership,
            action=SheetUpdateRequestType.DISTINCTION_ADD,
            distinction=distinction,
            reasoning="Earned it.",
        )
        with self.assertRaises(TableRequestError):
            signoff_table_update_request(request, self.gm, approve=True)

        request.refresh_from_db()
        assert request.status == TableRequestStatus.PENDING

    def test_reject_notifies_and_terminates(self):
        from world.narrative.models import NarrativeMessage

        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        before = NarrativeMessage.objects.count()
        signoff_table_update_request(request, self.gm, approve=False, notes="Not yet.")

        request.refresh_from_db()
        assert request.status == TableRequestStatus.REJECTED
        assert request.gm_notes == "Not yet."
        assert NarrativeMessage.objects.count() == before + 1

    def test_double_signoff_rejected(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        signoff_table_update_request(request, self.gm, approve=True)
        with self.assertRaises(TableRequestError):
            signoff_table_update_request(request, self.gm, approve=False)


class WithdrawTests(TestCase):
    def setUp(self):
        self.membership = GMTableMembershipFactory()
        self.gm = self.membership.table.gm

    def test_withdraw_pending(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        withdraw_table_update_request(request)
        request.refresh_from_db()
        assert request.status == TableRequestStatus.WITHDRAWN

    def test_withdraw_resolved_rejected(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        signoff_table_update_request(request, self.gm, approve=False)
        with self.assertRaises(TableRequestError):
            withdraw_table_update_request(request)
