"""Tests for the CheckProposal submission pipeline (#3295).

Covers the create -> staff-inbox -> resolve round trip: a player proposes a new
CheckType (never touching the live catalog), it surfaces in the staff inbox, and
staff resolve it (adopt/decline) with review notes. Adoption itself (authoring the
real CheckType row) is a separate, manual staff act this pipeline never automates.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.factories import CheckProposalFactory
from world.player_submissions.models import CheckProposal
from world.roster.factories import RosterTenureFactory


def _create_played_persona(account, key: str = "ProposerChar"):
    character = CharacterFactory(db_key=key)
    identity = CharacterSheetFactory(character=character)
    persona = identity.primary_persona
    RosterTenureFactory(
        roster_entry__character_sheet__character=character,
        player_data__account=account,
    )
    return character, persona


class CheckProposalCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="proposer")
        cls.character, cls.persona = _create_played_persona(cls.account)

    def test_authenticated_player_can_propose(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/check-proposals/",
            {
                "submitted_by_persona": self.persona.pk,
                "proposed_name": "Riverside Tracking",
                "intent": "Following a trail along the riverbank.",
                "suggested_traits_text": "Perception + Survival",
                "situation_text": "Chasing a fleeing target through wetlands.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        proposal = CheckProposal.objects.get()
        self.assertEqual(proposal.submitted_by_account, self.account)
        self.assertEqual(proposal.proposed_name, "Riverside Tracking")
        self.assertEqual(proposal.status, SubmissionStatus.OPEN)

    def test_cannot_propose_as_a_persona_you_do_not_play(self) -> None:
        other_account = AccountFactory(username="notproposer")
        client = APIClient()
        client.force_authenticate(user=other_account)
        response = client.post(
            "/api/player-submissions/check-proposals/",
            {
                "submitted_by_persona": self.persona.pk,
                "proposed_name": "Riverside Tracking",
                "intent": "Following a trail.",
                "situation_text": "Chasing a target.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_cannot_propose(self) -> None:
        client = APIClient()
        response = client.post(
            "/api/player-submissions/check-proposals/",
            {
                "submitted_by_persona": self.persona.pk,
                "proposed_name": "Riverside Tracking",
                "intent": "Following a trail.",
                "situation_text": "Chasing a target.",
            },
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_never_creates_a_live_check_type(self) -> None:
        """The catalog-only ruling: a proposal is never a CheckType row."""
        from world.checks.models import CheckType

        client = APIClient()
        client.force_authenticate(user=self.account)
        client.post(
            "/api/player-submissions/check-proposals/",
            {
                "submitted_by_persona": self.persona.pk,
                "proposed_name": "Riverside Tracking",
                "intent": "Following a trail.",
                "situation_text": "Chasing a target.",
            },
            format="json",
        )
        self.assertEqual(CheckType.objects.filter(name="Riverside Tracking").count(), 0)

    def test_regular_player_cannot_list_or_browse_proposals(self) -> None:
        """List/retrieve stay staff-only, same shape as BugReport/PlayerReport."""
        CheckProposalFactory()
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.get("/api/player-submissions/check-proposals/")
        self.assertEqual(response.status_code, 403)


class CheckProposalResolveTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="proposalstaff", is_staff=True)
        cls.regular = AccountFactory(username="proposalregular")
        cls.proposal = CheckProposalFactory()

    def test_staff_can_list_and_retrieve(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get("/api/player-submissions/check-proposals/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_staff_resolving_stamps_reviewer_and_resolved_at(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.patch(
            f"/api/player-submissions/check-proposals/{self.proposal.pk}/",
            {"status": SubmissionStatus.REVIEWED, "review_notes": "Adopted -- see CheckType #42."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SubmissionStatus.REVIEWED)
        self.assertEqual(self.proposal.reviewer, self.staff)
        self.assertIsNotNone(self.proposal.resolved_at)
        self.assertEqual(self.proposal.review_notes, "Adopted -- see CheckType #42.")

    def test_dismissing_a_proposal_also_stamps_reviewer(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.patch(
            f"/api/player-submissions/check-proposals/{self.proposal.pk}/",
            {"status": SubmissionStatus.DISMISSED, "review_notes": "Redundant with Athletics."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SubmissionStatus.DISMISSED)
        self.assertEqual(self.proposal.reviewer, self.staff)

    def test_regular_user_cannot_update(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.patch(
            f"/api/player-submissions/check-proposals/{self.proposal.pk}/",
            {"status": SubmissionStatus.REVIEWED},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_proposed_fields_are_read_only_on_update(self) -> None:
        """Staff can resolve, but cannot rewrite the player's own proposal text."""
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.patch(
            f"/api/player-submissions/check-proposals/{self.proposal.pk}/",
            {"proposed_name": "Tampered Name"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.proposal.refresh_from_db()
        self.assertNotEqual(self.proposal.proposed_name, "Tampered Name")
