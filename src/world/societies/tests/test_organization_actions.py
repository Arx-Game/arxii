"""Tests for the org lifecycle actions and telnet command (#1511)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.definitions.organizations import (
    org_apply_action,
    org_demote_action,
    org_expel_action,
    org_invite_action,
    org_join_action,
    org_leave_action,
    org_promote_action,
)
from actions.types import ActionResult, DispatchResult
from commands.organizations import CmdOrg
from evennia_extensions.factories import RoomProfileFactory
from world.roster.factories import RosterEntryFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipOfferFactory,
)
from world.societies.membership_services import join_organization
from world.societies.models import OrganizationMembershipOffer


class OrganizationActionTests(TestCase):
    def setUp(self):
        self.org = OrganizationFactory()
        self.manager_rank = self.org.ranks.get(tier=1)
        self.base_rank = self.org.ranks.order_by("-tier").first()

        self.actor_roster = RosterEntryFactory()
        self.actor = self.actor_roster.character_sheet.character
        self.actor_persona = self.actor_roster.character_sheet.primary_persona

        self.target_roster = RosterEntryFactory()
        self.target = self.target_roster.character_sheet.character
        self.target_persona = self.target_roster.character_sheet.primary_persona

        self.room = RoomProfileFactory().objectdb
        self.actor.move_to(self.room, quiet=True)
        self.target.move_to(self.room, quiet=True)

        # Make actor a manager.
        self.actor_membership = join_organization(self.org, self.actor_persona)
        self.actor_membership.rank = self.manager_rank
        self.actor_membership.save()

    def test_invite_action(self):
        result = org_invite_action.execute(
            self.actor,
            target=self.target,
            organization_id=self.org.pk,
        )
        assert result.success is True
        assert "invite" in result.message.lower()

    def test_join_action(self):
        OrganizationMembershipOfferFactory(
            organization=self.org,
            from_persona=self.actor_persona,
            to_persona=self.target_persona,
            kind=OrganizationMembershipOffer.Kind.INVITE,
        )
        result = org_join_action.execute(
            self.target,
            organization_id=self.org.pk,
        )
        assert result.success is True
        assert "join" in result.message.lower()

    def test_leave_action(self):
        membership = join_organization(self.org, self.target_persona)
        result = org_leave_action.execute(
            self.target,
            organization_id=self.org.pk,
        )
        assert result.success is True
        membership.refresh_from_db()
        assert membership.left_at is not None

    def test_apply_action(self):
        result = org_apply_action.execute(
            self.target,
            organization_id=self.org.pk,
        )
        assert result.success is True

    def test_promote_action(self):
        target_membership = join_organization(self.org, self.target_persona)
        result = org_promote_action.execute(
            self.actor,
            target=self.target,
            organization_id=self.org.pk,
        )
        assert result.success is True
        target_membership.refresh_from_db()
        assert target_membership.rank.tier == 4

    def test_demote_action(self):
        target_membership = join_organization(self.org, self.target_persona)
        target_membership.rank = self.org.ranks.get(tier=2)
        target_membership.save()
        result = org_demote_action.execute(
            self.actor,
            target=self.target,
            organization_id=self.org.pk,
        )
        assert result.success is True
        target_membership.refresh_from_db()
        assert target_membership.rank.tier == 3

    def test_expel_action(self):
        target_membership = join_organization(self.org, self.target_persona)
        result = org_expel_action.execute(
            self.actor,
            target=self.target,
            organization_id=self.org.pk,
        )
        assert result.success is True
        target_membership.refresh_from_db()
        assert target_membership.exiled_at is not None


_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdOrg:
    cmd = CmdOrg()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"org {args}"
    cmd.cmdname = "org"
    return cmd


class CmdOrgTests(TestCase):
    def test_resolve_action_ref_for_invite(self):
        cmd = _make_cmd("invite Alice in Testers")
        cmd._subverb = "invite"
        cmd._rest = "Alice in Testers"
        ref = cmd.resolve_action_ref()
        assert ref.backend == ActionBackend.REGISTRY
        assert ref.registry_key == "org_invite"

    def test_invite_subverb_dispatches(self):
        org = OrganizationFactory(name="Testers")
        target = MagicMock()
        caller = MagicMock()
        caller.search.return_value = target

        cmd = _make_cmd("invite Alice in Testers")
        cmd.caller = caller
        result = ActionResult(success=True, message="Invited.")
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=result,
        )

        with patch(_DISPATCH, return_value=dispatch_result) as mock_dispatch:
            cmd.func()

        mock_dispatch.assert_called_once()
        _, ref, kwargs = mock_dispatch.call_args.args
        assert ref.registry_key == "org_invite"
        assert kwargs["target"] is target
        assert kwargs["organization_id"] == org.pk

    def test_apply_subverb_dispatches(self):
        org = OrganizationFactory(name="Testers")
        cmd = _make_cmd("apply Testers")
        result = ActionResult(success=True, message="Applied.")
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=result,
        )

        with patch(_DISPATCH, return_value=dispatch_result) as mock_dispatch:
            cmd.func()

        mock_dispatch.assert_called_once()
        _, ref, kwargs = mock_dispatch.call_args.args
        assert ref.registry_key == "org_apply"
        assert kwargs["organization_id"] == org.pk

    def test_bare_org_shows_hub(self):
        cmd = _make_cmd("")
        cmd.func()
        cmd.caller.msg.assert_called_once()
        assert "Org actions" in cmd.caller.msg.call_args.args[0]
