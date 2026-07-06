"""Tests for the ritual-dispatched org-induction validator + service (#1868)."""

from datetime import UTC, datetime, timedelta

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import ParticipantState, ParticipationRule, ReferenceKind
from world.magic.exceptions import SessionTargetMissingError
from world.magic.factories import RitualFactory
from world.magic.models.sessions import (
    RitualSession,
    RitualSessionParticipant,
    RitualSessionReference,
)
from world.societies.exceptions import (
    NotAGenericOrganizationError,
    NotAuthorizedToLeadOrgRitualError,
)
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationTypeFactory,
)
from world.societies.models import OrganizationMembership


def _build_session(*, initiator_sheet, candidate_sheet, organization, ritual=None):
    ritual = ritual or RitualFactory(participation_rule=ParticipationRule.BILATERAL)
    session = RitualSession.objects.create(
        ritual=ritual,
        initiator=initiator_sheet,
        session_kwargs={},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    RitualSessionReference.objects.create(
        session=session,
        participant=None,
        kind=ReferenceKind.ORGANIZATION,
        ref_organization=organization,
    )
    RitualSessionParticipant.objects.create(
        session=session,
        character_sheet=initiator_sheet,
        state=ParticipantState.ACCEPTED,
    )
    RitualSessionParticipant.objects.create(
        session=session,
        character_sheet=candidate_sheet,
        state=ParticipantState.ACCEPTED,
    )
    return session


class AssertInitiatorCanLeadOrgRitualTests(TestCase):
    def test_leader_rank_passes(self):
        from world.societies.membership_services import assert_initiator_can_lead_org_ritual

        org = OrganizationFactory()
        leader_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=org,
            persona=leader_sheet.primary_persona,
            rank=1,
        )
        candidate_sheet = CharacterSheetFactory()
        session = _build_session(
            initiator_sheet=leader_sheet, candidate_sheet=candidate_sheet, organization=org
        )
        # No exception:
        assert_initiator_can_lead_org_ritual(session=session)

    def test_non_leader_rank_raises(self):
        from world.societies.membership_services import assert_initiator_can_lead_org_ritual

        org = OrganizationFactory()
        member_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=org,
            persona=member_sheet.primary_persona,
            rank=5,
        )
        candidate_sheet = CharacterSheetFactory()
        session = _build_session(
            initiator_sheet=member_sheet, candidate_sheet=candidate_sheet, organization=org
        )
        with self.assertRaises(NotAuthorizedToLeadOrgRitualError):
            assert_initiator_can_lead_org_ritual(session=session)

    def test_non_member_initiator_raises(self):
        from world.societies.membership_services import assert_initiator_can_lead_org_ritual

        org = OrganizationFactory()
        outsider_sheet = CharacterSheetFactory()
        candidate_sheet = CharacterSheetFactory()
        session = _build_session(
            initiator_sheet=outsider_sheet, candidate_sheet=candidate_sheet, organization=org
        )
        with self.assertRaises(NotAuthorizedToLeadOrgRitualError):
            assert_initiator_can_lead_org_ritual(session=session)

    def test_covenant_organization_raises(self):
        from world.societies.membership_services import assert_initiator_can_lead_org_ritual

        covenant_org = OrganizationFactory(org_type=OrganizationTypeFactory(name="covenant"))
        leader_sheet = CharacterSheetFactory()
        candidate_sheet = CharacterSheetFactory()
        session = _build_session(
            initiator_sheet=leader_sheet, candidate_sheet=candidate_sheet, organization=covenant_org
        )
        with self.assertRaises(NotAGenericOrganizationError):
            assert_initiator_can_lead_org_ritual(session=session)

    def test_missing_organization_reference_raises(self):
        from world.societies.membership_services import assert_initiator_can_lead_org_ritual

        ritual = RitualFactory(participation_rule=ParticipationRule.BILATERAL)
        initiator_sheet = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator_sheet,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        with self.assertRaises(SessionTargetMissingError):
            assert_initiator_can_lead_org_ritual(session=session)


class InductOrganizationMemberViaSessionTests(TestCase):
    def test_fires_and_creates_membership(self):
        from world.societies.membership_services import induct_organization_member_via_session

        org = OrganizationFactory()
        leader_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=org,
            persona=leader_sheet.primary_persona,
            rank=1,
        )
        candidate_sheet = CharacterSheetFactory()
        session = _build_session(
            initiator_sheet=leader_sheet, candidate_sheet=candidate_sheet, organization=org
        )
        membership = induct_organization_member_via_session(session=session)
        self.assertIsInstance(membership, OrganizationMembership)
        self.assertEqual(membership.persona, candidate_sheet.primary_persona)
        self.assertEqual(membership.organization, org)
        self.assertIsNone(membership.left_at)

    def test_missing_organization_reference_raises(self):
        from world.societies.membership_services import induct_organization_member_via_session

        ritual = RitualFactory(participation_rule=ParticipationRule.BILATERAL)
        initiator_sheet = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator_sheet,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        with self.assertRaises(SessionTargetMissingError):
            induct_organization_member_via_session(session=session)
