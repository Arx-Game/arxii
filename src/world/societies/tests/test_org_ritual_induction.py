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


class OrganizationInductionJourneyTests(TestCase):
    """Highest-seam journey test: draft -> accept -> fire, exactly as a player
    would experience it via CmdRitual + OrganizationInductionAdapter."""

    def test_full_journey_creates_membership(self):
        from datetime import UTC, datetime, timedelta

        from commands.ritual_adapters import get_adapter
        from world.magic.factories import OrganizationInductionRitualFactory
        from world.magic.services.sessions import accept_session, draft_session, fire_session

        org = OrganizationFactory()
        leader_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=org,
            persona=leader_sheet.primary_persona,
            rank=1,
        )
        candidate_sheet = CharacterSheetFactory()
        ritual = OrganizationInductionRitualFactory()

        adapter = get_adapter(ritual)
        draft_parse = adapter.parse_draft(kwargs={"organization": org.name}, caller=None)

        session = draft_session(
            ritual=ritual,
            initiator=leader_sheet,
            proposed_terms="",
            session_kwargs=draft_parse.session_kwargs,
            invitee_sheets=[candidate_sheet],
            session_references=draft_parse.session_references,
            initiator_participant_kwargs=draft_parse.initiator_participant_kwargs,
            initiator_references=draft_parse.initiator_references,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        candidate_p = session.participants.get(character_sheet=candidate_sheet)
        accept_session(participant=candidate_p, participant_kwargs={}, references=[])

        membership = fire_session(session=session)

        self.assertEqual(membership.persona, candidate_sheet.primary_persona)
        self.assertEqual(membership.organization, org)
        self.assertTrue(
            OrganizationMembership.objects.filter(
                organization=org, persona=candidate_sheet.primary_persona, left_at__isnull=True
            ).exists()
        )
        # Session is deleted on fire (CASCADE):
        self.assertFalse(RitualSession.objects.filter(pk=session.pk).exists())

    def test_unauthorized_officiant_rejected_at_draft(self):
        from datetime import UTC, datetime, timedelta

        from commands.ritual_adapters import get_adapter
        from world.magic.factories import OrganizationInductionRitualFactory
        from world.magic.services.sessions import draft_session
        from world.societies.exceptions import NotAuthorizedToLeadOrgRitualError

        org = OrganizationFactory()
        member_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=org, persona=member_sheet.primary_persona, rank=5
        )
        candidate_sheet = CharacterSheetFactory()
        ritual = OrganizationInductionRitualFactory()

        adapter = get_adapter(ritual)
        draft_parse = adapter.parse_draft(kwargs={"organization": org.name}, caller=None)

        with self.assertRaises(NotAuthorizedToLeadOrgRitualError):
            draft_session(
                ritual=ritual,
                initiator=member_sheet,
                proposed_terms="",
                session_kwargs=draft_parse.session_kwargs,
                invitee_sheets=[candidate_sheet],
                session_references=draft_parse.session_references,
                initiator_participant_kwargs=draft_parse.initiator_participant_kwargs,
                initiator_references=draft_parse.initiator_references,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        # No session persisted — draft_session's transaction rolled back:
        self.assertEqual(RitualSession.objects.filter(ritual=ritual).count(), 0)
