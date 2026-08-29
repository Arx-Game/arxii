"""DRF tests for ``OrganizationMembershipOfferViewSet.respond`` (#3412 — the Hall).

INVITE offers: the invitee (``to_persona``'s owning account) responds.
APPLICATION offers: an org member with invite authority responds on behalf
of the organization. Covers accept/decline happy paths for both kinds, the
wrong-account/unauthorized rejections, and an already-resolved offer.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationMembershipOfferFactory,
)
from world.societies.models import OrganizationMembershipOffer


def _active_primary_persona(*, account):
    """Create a character sheet + active tenure and return its primary persona.

    Mirrors ``test_org_appeal_api.py``'s helper of the same name — the
    established pattern in this app for "give this account a persona it owns"
    in a REST test.
    """
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    roster = RosterFactory()
    entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
    player_data = PlayerData.objects.create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    entry.invalidate_tenure_cache()
    return sheet.primary_persona


def _respond_url(offer_id: int) -> str:
    return reverse("societies:organization-membership-offer-respond", args=[offer_id])


class InviteOfferRespondTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.org = OrganizationFactory(name="Invite Testers")

        self.inviter_account = AccountFactory()
        self.inviter_persona = _active_primary_persona(account=self.inviter_account)
        OrganizationMembershipFactory(
            organization=self.org,
            persona=self.inviter_persona,
            rank=self.org.ranks.get(tier=1),
        )

        self.invitee_account = AccountFactory()
        self.invitee_persona = _active_primary_persona(account=self.invitee_account)

        # A fellow member (visible via org_visible, so `get_object()` succeeds)
        # who is neither the inviter nor the invitee — the true "wrong account"
        # case, distinct from a stranger who can't see the offer at all (404).
        self.outsider_account = AccountFactory()
        self.outsider_persona = _active_primary_persona(account=self.outsider_account)
        OrganizationMembershipFactory(
            organization=self.org,
            persona=self.outsider_persona,
            rank=self.org.ranks.get(tier=5),
        )

        self.stranger_account = AccountFactory()
        _active_primary_persona(account=self.stranger_account)

        self.offer = OrganizationMembershipOfferFactory(
            organization=self.org,
            from_persona=self.inviter_persona,
            to_persona=self.invitee_persona,
            kind=OrganizationMembershipOffer.Kind.INVITE,
        )

    def test_invitee_accepts(self) -> None:
        self.client.force_authenticate(user=self.invitee_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OrganizationMembershipOffer.Status.ACCEPTED)
        self.assertTrue(
            self.org.memberships.filter(persona=self.invitee_persona, left_at__isnull=True).exists()
        )

    def test_invitee_declines(self) -> None:
        self.client.force_authenticate(user=self.invitee_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "decline"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OrganizationMembershipOffer.Status.DECLINED)

    def test_wrong_account_rejected(self) -> None:
        self.client.force_authenticate(user=self.outsider_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OrganizationMembershipOffer.Status.PENDING)

    def test_stranger_gets_404_not_403(self) -> None:
        """An account with no visibility into the offer (not owned, not org
        member) never reaches the ownership check — `get_object()`'s own
        queryset filtering 404s it first, same as any other DRF detail view."""
        self.client.force_authenticate(user=self.stranger_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inviter_cannot_respond_to_own_invite(self) -> None:
        self.client.force_authenticate(user=self.inviter_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_response_value_rejected(self) -> None:
        self.client.force_authenticate(user=self.invitee_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "maybe"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_resolved_offer_rejected(self) -> None:
        self.client.force_authenticate(user=self.invitee_account)
        first = self.client.post(
            _respond_url(self.offer.pk), {"response": "decline"}, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)


class ApplicationOfferRespondTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.org = OrganizationFactory(name="Application Testers")

        self.officer_account = AccountFactory()
        self.officer_persona = _active_primary_persona(account=self.officer_account)
        OrganizationMembershipFactory(
            organization=self.org,
            persona=self.officer_persona,
            rank=self.org.ranks.get(tier=1),
        )

        self.rankfile_account = AccountFactory()
        self.rankfile_persona = _active_primary_persona(account=self.rankfile_account)
        OrganizationMembershipFactory(
            organization=self.org,
            persona=self.rankfile_persona,
            rank=self.org.ranks.get(tier=5),
        )

        self.applicant_account = AccountFactory()
        self.applicant_persona = _active_primary_persona(account=self.applicant_account)

        self.offer = OrganizationMembershipOfferFactory(
            organization=self.org,
            from_persona=self.applicant_persona,
            to_persona=None,
            kind=OrganizationMembershipOffer.Kind.APPLICATION,
        )

    def test_officer_accepts(self) -> None:
        self.client.force_authenticate(user=self.officer_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OrganizationMembershipOffer.Status.ACCEPTED)
        self.assertTrue(
            self.org.memberships.filter(
                persona=self.applicant_persona, left_at__isnull=True
            ).exists()
        )

    def test_officer_declines(self) -> None:
        self.client.force_authenticate(user=self.officer_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "decline"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OrganizationMembershipOffer.Status.DECLINED)

    def test_rank_and_file_member_lacks_authority(self) -> None:
        self.client.force_authenticate(user=self.rankfile_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_applicant_cannot_respond_to_own_application(self) -> None:
        self.client.force_authenticate(user=self.applicant_account)
        response = self.client.post(
            _respond_url(self.offer.pk), {"response": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
