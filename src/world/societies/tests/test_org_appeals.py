"""Tests for appeals to organizations (#3293): models, services, actions, telnet."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.db import IntegrityError, transaction
from django.test import TestCase

from actions.constants import ActionBackend
from actions.definitions.org_appeals import (
    org_appeal_lodge_action,
    org_appeal_resolve_action,
    org_appeal_signon_action,
    org_appeal_withdraw_action,
)
from actions.types import ActionResult, DispatchResult
from commands.organizations import CmdAppeal
from world.roster.factories import RosterEntryFactory, grant_test_tenure
from world.societies.appeal_services import (
    can_resolve_org_appeals,
    lodge_appeal,
    resolve_appeal,
    signon_appeal,
    withdraw_appeal,
)
from world.societies.constants import OrgAppealState
from world.societies.exceptions import (
    AppealNotOpenError,
    InvalidAppealVerdictError,
    NotAppealPetitionerError,
    NotAuthorizedToResolveAppealError,
    NotOrganizationMemberError,
)
from world.societies.factories import OrganizationFactory, OrgAppealFactory
from world.societies.membership_services import join_organization
from world.societies.models import OrgAppeal, OrgAppealSignon


class OrgAppealServiceTests(TestCase):
    """Service-layer tests for lodge/signon/resolve/withdraw."""

    def setUp(self):
        self.org = OrganizationFactory()
        self.leader_rank = self.org.ranks.get(tier=1)
        self.member_rank = self.org.ranks.order_by("-tier").first()

        self.petitioner_roster = RosterEntryFactory()
        self.petitioner_persona = self.petitioner_roster.character_sheet.primary_persona

        self.member_roster = RosterEntryFactory()
        self.member_persona = self.member_roster.character_sheet.primary_persona
        self.membership = join_organization(self.org, self.member_persona)

        self.leader_roster = RosterEntryFactory()
        self.leader_persona = self.leader_roster.character_sheet.primary_persona
        self.leader_membership = join_organization(self.org, self.leader_persona)
        self.leader_membership.rank = self.leader_rank
        self.leader_membership.save()

    def test_lodge_appeal_creates_open_row(self):
        appeal = lodge_appeal(
            organization=self.org,
            petitioner_persona=self.petitioner_persona,
            title="Aid against bandits",
            body="Our village needs help.",
        )
        assert appeal.state == OrgAppealState.OPEN
        assert appeal.organization_id == self.org.pk
        assert appeal.petitioner_persona_id == self.petitioner_persona.pk

    def test_lodge_appeal_does_not_require_membership(self):
        """Any character may lodge — no membership row exists for the petitioner."""
        appeal = lodge_appeal(
            organization=self.org,
            petitioner_persona=self.petitioner_persona,
            title="A stranger's plea",
            body="I know no one here.",
        )
        assert appeal.pk is not None

    def test_second_open_appeal_same_petitioner_raises(self):
        """Partial unique constraint: one OPEN appeal per (org, petitioner)."""
        lodge_appeal(
            organization=self.org,
            petitioner_persona=self.petitioner_persona,
            title="First ask",
            body="Body one.",
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            lodge_appeal(
                organization=self.org,
                petitioner_persona=self.petitioner_persona,
                title="Second ask",
                body="Body two.",
            )

    def test_withdrawn_then_new_open_appeal_is_ok(self):
        first = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        withdraw_appeal(appeal=first, petitioner_persona=self.petitioner_persona)
        second = lodge_appeal(
            organization=self.org,
            petitioner_persona=self.petitioner_persona,
            title="Another ask",
            body="Body.",
        )
        assert second.pk is not None

    def test_signon_by_member_succeeds(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        signon = signon_appeal(appeal=appeal, member_persona=self.member_persona, note="I vouch.")
        assert isinstance(signon, OrgAppealSignon)
        assert signon.appeal_id == appeal.pk
        assert signon.note == "I vouch."

    def test_signon_by_non_member_raises(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        outsider = RosterEntryFactory().character_sheet.primary_persona
        with self.assertRaises(NotOrganizationMemberError):
            signon_appeal(appeal=appeal, member_persona=outsider)

    def test_signon_on_resolved_appeal_raises(self):
        appeal = OrgAppealFactory(
            organization=self.org,
            petitioner_persona=self.petitioner_persona,
            state=OrgAppealState.GRANTED,
        )
        with self.assertRaises(AppealNotOpenError):
            signon_appeal(appeal=appeal, member_persona=self.member_persona)

    def test_signon_is_idempotent(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        first = signon_appeal(appeal=appeal, member_persona=self.member_persona)
        second = signon_appeal(appeal=appeal, member_persona=self.member_persona)
        assert first.pk == second.pk
        assert OrgAppealSignon.objects.filter(appeal=appeal).count() == 1

    def test_can_resolve_org_appeals_true_for_leader_false_for_member(self):
        assert can_resolve_org_appeals(self.leader_persona, self.org) is True
        assert can_resolve_org_appeals(self.member_persona, self.org) is False

    def test_resolve_by_leader_grants(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        resolved = resolve_appeal(
            appeal=appeal,
            verdict=OrgAppealState.GRANTED,
            resolution_text="Help is on the way.",
            resolver_persona=self.leader_persona,
        )
        assert resolved.state == OrgAppealState.GRANTED
        assert resolved.resolution_text == "Help is on the way."
        assert resolved.resolved_by_persona_id == self.leader_persona.pk
        assert resolved.resolved_at is not None

    def test_resolve_by_non_privileged_member_raises(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        with self.assertRaises(NotAuthorizedToResolveAppealError):
            resolve_appeal(
                appeal=appeal,
                verdict=OrgAppealState.DECLINED,
                resolution_text="No.",
                resolver_persona=self.member_persona,
            )

    def test_resolve_by_staff_bypasses_rank_check(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        resolved = resolve_appeal(
            appeal=appeal,
            verdict=OrgAppealState.DECLINED,
            resolution_text="Staff call.",
            resolver_persona=self.member_persona,
            is_staff=True,
        )
        assert resolved.state == OrgAppealState.DECLINED

    def test_resolve_invalid_verdict_raises(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        with self.assertRaises(InvalidAppealVerdictError):
            resolve_appeal(
                appeal=appeal,
                verdict=OrgAppealState.WITHDRAWN,
                resolution_text="",
                resolver_persona=self.leader_persona,
            )

    def test_resolve_already_resolved_raises(self):
        appeal = OrgAppealFactory(
            organization=self.org,
            petitioner_persona=self.petitioner_persona,
            state=OrgAppealState.GRANTED,
        )
        with self.assertRaises(AppealNotOpenError):
            resolve_appeal(
                appeal=appeal,
                verdict=OrgAppealState.DECLINED,
                resolution_text="Too late.",
                resolver_persona=self.leader_persona,
            )

    def test_withdraw_by_petitioner_succeeds(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        withdrawn = withdraw_appeal(appeal=appeal, petitioner_persona=self.petitioner_persona)
        assert withdrawn.state == OrgAppealState.WITHDRAWN
        assert withdrawn.resolved_at is not None

    def test_withdraw_by_non_petitioner_raises(self):
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        with self.assertRaises(NotAppealPetitionerError):
            withdraw_appeal(appeal=appeal, petitioner_persona=self.member_persona)


class OrgAppealActionTests(TestCase):
    """Action-layer tests, mirroring ``test_organization_actions.py``."""

    def setUp(self):
        self.org = OrganizationFactory(name="Testers Guild")
        self.leader_rank = self.org.ranks.get(tier=1)

        self.petitioner_roster = RosterEntryFactory()
        self.petitioner = self.petitioner_roster.character_sheet.character
        self.petitioner_persona = self.petitioner_roster.character_sheet.primary_persona

        self.member_roster = RosterEntryFactory()
        self.member = self.member_roster.character_sheet.character
        self.member_persona = self.member_roster.character_sheet.primary_persona
        join_organization(self.org, self.member_persona)

        self.leader_roster = RosterEntryFactory()
        self.leader = self.leader_roster.character_sheet.character
        self.leader_persona = self.leader_roster.character_sheet.primary_persona
        self.leader_membership = join_organization(self.org, self.leader_persona)
        self.leader_membership.rank = self.leader_rank
        self.leader_membership.save()

    def test_lodge_action(self):
        result = org_appeal_lodge_action.execute(
            self.petitioner,
            organization_id=self.org.pk,
            title="Bandits on the road",
            body="Send aid.",
        )
        assert result.success is True
        assert "appeal" in result.message.lower()
        appeal_id = result.data["appeal_id"]
        assert OrgAppeal.objects.filter(pk=appeal_id, organization=self.org).exists()

    def test_lodge_action_requires_title_and_body(self):
        missing_title = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="", body="Body"
        )
        assert missing_title.success is False
        missing_body = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="Title", body=""
        )
        assert missing_body.success is False

    def test_full_journey_lodge_signon_resolve_read(self):
        """Outsider lodges -> member signs on -> leadership grants -> petitioner reads it."""
        lodge_result = org_appeal_lodge_action.execute(
            self.petitioner,
            organization_id=self.org.pk,
            title="Bandits on the road",
            body="Send aid.",
        )
        assert lodge_result.success is True
        appeal_id = lodge_result.data["appeal_id"]

        signon_result = org_appeal_signon_action.execute(
            self.member, appeal_id=appeal_id, note="I'll ride with you."
        )
        assert signon_result.success is True
        assert OrgAppealSignon.objects.filter(
            appeal_id=appeal_id, member_persona=self.member_persona
        ).exists()

        resolve_result = org_appeal_resolve_action.execute(
            self.leader, appeal_id=appeal_id, verdict="grant", answer="Guards are dispatched."
        )
        assert resolve_result.success is True

        appeal = OrgAppeal.objects.get(pk=appeal_id)
        assert appeal.state == OrgAppealState.GRANTED
        assert appeal.resolution_text == "Guards are dispatched."
        assert appeal.resolved_by_persona_id == self.leader_persona.pk

    def test_signon_action_requires_membership(self):
        lodge_result = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="T", body="B"
        )
        outsider_roster = RosterEntryFactory()
        outsider = outsider_roster.character_sheet.character
        result = org_appeal_signon_action.execute(
            outsider, appeal_id=lodge_result.data["appeal_id"]
        )
        assert result.success is False
        assert "member" in result.message.lower()

    def test_resolve_action_rejects_non_privileged_member(self):
        lodge_result = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="T", body="B"
        )
        result = org_appeal_resolve_action.execute(
            self.member,
            appeal_id=lodge_result.data["appeal_id"],
            verdict="grant",
            answer="",
        )
        assert result.success is False
        assert "authorized" in result.message.lower()

    def test_resolve_action_allows_staff_without_rank(self):
        lodge_result = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="T", body="B"
        )
        tenure = grant_test_tenure(self.member_roster.character_sheet)
        tenure.player_data.account.is_staff = True
        tenure.player_data.account.save()

        result = org_appeal_resolve_action.execute(
            self.member,
            appeal_id=lodge_result.data["appeal_id"],
            verdict="decline",
            answer="Staff call.",
        )
        assert result.success is True

    def test_resolve_action_requires_verdict(self):
        lodge_result = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="T", body="B"
        )
        result = org_appeal_resolve_action.execute(
            self.leader,
            appeal_id=lodge_result.data["appeal_id"],
            verdict="",
            answer="",
        )
        assert result.success is False

    def test_withdraw_action_by_petitioner(self):
        lodge_result = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="T", body="B"
        )
        result = org_appeal_withdraw_action.execute(
            self.petitioner, appeal_id=lodge_result.data["appeal_id"]
        )
        assert result.success is True
        appeal = OrgAppeal.objects.get(pk=lodge_result.data["appeal_id"])
        assert appeal.state == OrgAppealState.WITHDRAWN

    def test_withdraw_action_rejects_non_petitioner(self):
        lodge_result = org_appeal_lodge_action.execute(
            self.petitioner, organization_id=self.org.pk, title="T", body="B"
        )
        result = org_appeal_withdraw_action.execute(
            self.member, appeal_id=lodge_result.data["appeal_id"]
        )
        assert result.success is False
        assert "own" in result.message.lower()


_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdAppeal:
    cmd = CmdAppeal()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"appeal {args}"
    cmd.cmdname = "appeal"
    return cmd


class CmdAppealTests(TestCase):
    def setUp(self):
        self.org = OrganizationFactory(name="Testers Guild")

    def test_bare_appeal_shows_hub(self):
        cmd = _make_cmd("")
        cmd.func()
        cmd.caller.msg.assert_called_once()
        assert "Appeal actions" in cmd.caller.msg.call_args.args[0]

    def test_lodge_grammar_dispatches(self):
        cmd = _make_cmd("Testers Guild=Aid needed/Bandits on the road, please help.")
        result = ActionResult(success=True, message="Lodged.")
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY, deferred=False, detail=result
        )
        with patch(_DISPATCH, return_value=dispatch_result) as mock_dispatch:
            cmd.func()

        mock_dispatch.assert_called_once()
        _, ref, kwargs = mock_dispatch.call_args.args
        assert ref.registry_key == "org_appeal_lodge"
        assert kwargs["organization_id"] == self.org.pk
        assert kwargs["title"] == "Aid needed"
        assert kwargs["body"] == "Bandits on the road, please help."

    def test_signon_grammar_dispatches_with_note(self):
        cmd = _make_cmd("signon 7=I vouch for this.")
        result = ActionResult(success=True, message="Signed on.")
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY, deferred=False, detail=result
        )
        with patch(_DISPATCH, return_value=dispatch_result) as mock_dispatch:
            cmd.func()

        _, ref, kwargs = mock_dispatch.call_args.args
        assert ref.registry_key == "org_appeal_signon"
        assert kwargs["appeal_id"] == 7
        assert kwargs["note"] == "I vouch for this."

    def test_signon_grammar_without_note(self):
        cmd = _make_cmd("signon 7")
        result = ActionResult(success=True, message="Signed on.")
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY, deferred=False, detail=result
        )
        with patch(_DISPATCH, return_value=dispatch_result) as mock_dispatch:
            cmd.func()

        _, _ref, kwargs = mock_dispatch.call_args.args
        assert kwargs["appeal_id"] == 7
        assert kwargs["note"] == ""

    def test_resolve_grammar_dispatches(self):
        cmd = _make_cmd("resolve 3=grant/Guards are on the way.")
        result = ActionResult(success=True, message="Granted.")
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY, deferred=False, detail=result
        )
        with patch(_DISPATCH, return_value=dispatch_result) as mock_dispatch:
            cmd.func()

        _, ref, kwargs = mock_dispatch.call_args.args
        assert ref.registry_key == "org_appeal_resolve"
        assert kwargs["appeal_id"] == 3
        assert kwargs["verdict"] == "grant"
        assert kwargs["answer"] == "Guards are on the way."

    def test_withdraw_grammar_dispatches(self):
        cmd = _make_cmd("withdraw 9")
        result = ActionResult(success=True, message="Withdrawn.")
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY, deferred=False, detail=result
        )
        with patch(_DISPATCH, return_value=dispatch_result) as mock_dispatch:
            cmd.func()

        _, ref, kwargs = mock_dispatch.call_args.args
        assert ref.registry_key == "org_appeal_withdraw"
        assert kwargs["appeal_id"] == 9

    def test_withdraw_rejects_non_numeric_id(self):
        cmd = _make_cmd("withdraw not-a-number")
        cmd.func()
        cmd.caller.msg.assert_called_once()
        assert "numeric" in cmd.caller.msg.call_args.args[0].lower()
