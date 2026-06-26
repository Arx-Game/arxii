"""Tests for the generic organization membership lifecycle (#1511)."""

from django.test import TestCase
import pytest

from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.exceptions import (
    AlreadyOrganizationMemberError,
    NotAGenericOrganizationError,
    NotAuthorizedToInviteError,
    NotAuthorizedToKickError,
    NotAuthorizedToManageRanksError,
)
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.membership_services import (
    accept_application,
    accept_invitation,
    apply_to_organization,
    base_rank_for_organization,
    decline_application,
    decline_invitation,
    demote_member,
    expel_member,
    invite_to_organization,
    join_organization,
    leave_organization,
    promote_member,
)
from world.societies.models import OrganizationMembershipOffer


class RankLadderTests(TestCase):
    def test_default_ladder_created_on_save(self):
        org = OrganizationFactory()
        ranks = list(org.ranks.order_by("tier"))
        assert len(ranks) == 5
        assert ranks[0].tier == 1
        assert ranks[-1].tier == 5


class MembershipLifecycleTests(TestCase):
    def setUp(self):
        self.org = OrganizationFactory()
        self.base_rank = base_rank_for_organization(self.org)
        self.manager_rank = self.org.ranks.get(tier=1)
        self.member = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        self.manager = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        self.base_member = PersonaFactory(persona_type=PersonaType.ESTABLISHED)

        # Set up the manager at the top rank.
        self.manager_membership = join_organization(self.org, self.manager)
        self.manager_membership.rank = self.manager_rank
        self.manager_membership.save()

        # Set up a non-manager member for authorization tests.
        self.base_member_membership = join_organization(self.org, self.base_member)

    def test_join_creates_active_membership(self):
        membership = join_organization(self.org, self.member)
        assert membership.organization == self.org
        assert membership.persona == self.member
        assert membership.rank == self.base_rank

    def test_active_membership_unique(self):
        join_organization(self.org, self.member)
        with pytest.raises(AlreadyOrganizationMemberError):
            join_organization(self.org, self.member)

    def test_invite_and_accept(self):
        invite = invite_to_organization(self.org, self.manager, self.member)
        assert invite.status == OrganizationMembershipOffer.Status.PENDING
        membership = accept_invitation(invite, self.member)
        assert membership.rank == self.base_rank
        invite.refresh_from_db()
        assert invite.status == OrganizationMembershipOffer.Status.ACCEPTED

    def test_invite_and_decline(self):
        invite = invite_to_organization(self.org, self.manager, self.member)
        decline_invitation(invite, self.member)
        invite.refresh_from_db()
        assert invite.status == OrganizationMembershipOffer.Status.DECLINED

    def test_apply_and_accept(self):
        apply = apply_to_organization(self.org, self.member)
        assert apply.kind == OrganizationMembershipOffer.Kind.APPLICATION
        membership = accept_application(apply, self.manager)
        assert membership.rank == self.base_rank
        apply.refresh_from_db()
        assert apply.status == OrganizationMembershipOffer.Status.ACCEPTED

    def test_apply_and_decline(self):
        apply = apply_to_organization(self.org, self.member)
        decline_application(apply, self.manager)
        apply.refresh_from_db()
        assert apply.status == OrganizationMembershipOffer.Status.DECLINED

    def test_leave_marks_left_at(self):
        membership = join_organization(self.org, self.member)
        leave_organization(membership)
        membership.refresh_from_db()
        assert membership.left_at is not None
        assert membership.exiled_at is None

    def test_promote_and_demote(self):
        target = join_organization(self.org, self.member)
        promote_member(target, self.manager_membership)
        target.refresh_from_db()
        assert target.rank.tier == 4
        demote_member(target, self.manager_membership)
        target.refresh_from_db()
        assert target.rank.tier == 5

    def test_expel_marks_exiled_and_left(self):
        target = join_organization(self.org, self.member)
        expel_member(target, self.manager_membership)
        target.refresh_from_db()
        assert target.left_at is not None
        assert target.exiled_at is not None

    def test_non_inviter_cannot_invite(self):
        non_manager = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        with pytest.raises(NotAuthorizedToInviteError):
            invite_to_organization(self.org, non_manager, self.member)

    def test_non_manager_cannot_promote(self):
        target = join_organization(self.org, self.member)
        with pytest.raises(NotAuthorizedToManageRanksError):
            promote_member(target, self.base_member_membership)

    def test_non_kicker_cannot_expel(self):
        target = join_organization(self.org, self.member)
        with pytest.raises(NotAuthorizedToKickError):
            expel_member(target, self.base_member_membership)


class CovenantGuardTests(TestCase):
    def setUp(self):
        self.covenant_org = OrganizationFactory(
            org_type=OrganizationTypeFactory(name="covenant"),
        )
        self.member = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        self.manager = PersonaFactory(persona_type=PersonaType.ESTABLISHED)

    def test_join_organization_rejects_covenant(self):
        with pytest.raises(NotAGenericOrganizationError):
            join_organization(self.covenant_org, self.member)

    def test_invite_to_organization_rejects_covenant(self):
        with pytest.raises(NotAGenericOrganizationError):
            invite_to_organization(self.covenant_org, self.manager, self.member)

    def test_apply_to_organization_rejects_covenant(self):
        with pytest.raises(NotAGenericOrganizationError):
            apply_to_organization(self.covenant_org, self.member)
