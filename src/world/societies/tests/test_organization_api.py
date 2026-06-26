"""DRF tests for the societies organization membership API (#1511)."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CovenantFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationMembershipOfferFactory,
    OrganizationRankFactory,
)


def _active_primary_persona(*, account):
    """Create a character sheet + active tenure and return its primary persona."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    roster = RosterFactory()
    RosterEntryFactory(character_sheet=sheet, roster=roster)
    player_data = PlayerData.objects.create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=sheet.roster_entry)
    return sheet.primary_persona


def _covenant_membership(*, account, persona):
    """Create a covenant-backed organization and an active membership for ``persona``."""
    covenant = CovenantFactory(name="Test Covenant")
    org = covenant.organization
    rank = OrganizationRankFactory(organization=org, tier=5, name="Member")
    return OrganizationMembershipFactory(organization=org, persona=persona, rank=rank)


class OrganizationApiTests(TestCase):
    """Tests for the /api/societies/organizations/ endpoint."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.persona = _active_primary_persona(account=self.account)
        self.organization = OrganizationFactory(name="Regular Org")
        OrganizationMembershipFactory(organization=self.organization, persona=self.persona)

    def test_list_shows_memberships_and_excludes_covenants(self) -> None:
        """Authenticated users see organizations they belong to; covenants are excluded."""
        cov_membership = _covenant_membership(account=self.account, persona=self.persona)

        response = self.client.get(reverse("societies:organization-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [org["id"] for org in response.data["results"]]
        self.assertIn(self.organization.id, ids)
        self.assertNotIn(cov_membership.organization.id, ids)

    def test_staff_sees_all_non_covenant_organizations(self) -> None:
        """Staff users see every non-covenant organization, regardless of membership."""
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)
        cov_membership = _covenant_membership(account=self.account, persona=self.persona)
        other_org = OrganizationFactory(name="Other Org")

        response = self.client.get(reverse("societies:organization-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [org["id"] for org in response.data["results"]]
        self.assertIn(self.organization.id, ids)
        self.assertIn(other_org.id, ids)
        self.assertNotIn(cov_membership.organization.id, ids)

    def test_unauthenticated_requests_are_rejected(self) -> None:
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse("societies:organization-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class OrganizationMembershipApiTests(TestCase):
    """Tests for the /api/societies/memberships/ endpoint."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.persona = _active_primary_persona(account=self.account)
        self.organization = OrganizationFactory(name="Member Org")
        self.membership = OrganizationMembershipFactory(
            organization=self.organization,
            persona=self.persona,
        )

    def test_list_own_memberships(self) -> None:
        """Users can list their own organization memberships."""
        other_account = AccountFactory()
        other_persona = _active_primary_persona(account=other_account)
        other_org = OrganizationFactory(name="Other Org")
        OrganizationMembershipFactory(organization=other_org, persona=other_persona)

        response = self.client.get(reverse("societies:organization-membership-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id"] for m in response.data["results"]]
        self.assertIn(self.membership.id, ids)
        self.assertNotIn(other_org.memberships.first().id, ids)

    def test_filter_by_organization(self) -> None:
        other_org = OrganizationFactory(name="Other Org")
        OrganizationMembershipFactory(organization=other_org, persona=self.persona)

        response = self.client.get(
            reverse("societies:organization-membership-list"),
            {"organization": self.organization.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id"] for m in response.data["results"]]
        self.assertIn(self.membership.id, ids)
        self.assertEqual(len(ids), 1)

    def test_filter_by_is_active(self) -> None:
        inactive = OrganizationMembershipFactory(
            organization=OrganizationFactory(name="Inactive Org"),
            persona=self.persona,
        )
        inactive.left_at = timezone.now()
        inactive.save(update_fields=["left_at"])

        active_response = self.client.get(
            reverse("societies:organization-membership-list"),
            {"is_active": "true"},
        )
        self.assertEqual(active_response.status_code, status.HTTP_200_OK)
        active_ids = [m["id"] for m in active_response.data["results"]]
        self.assertIn(self.membership.id, active_ids)
        self.assertNotIn(inactive.id, active_ids)

        inactive_response = self.client.get(
            reverse("societies:organization-membership-list"),
            {"is_active": "false"},
        )
        self.assertEqual(inactive_response.status_code, status.HTTP_200_OK)
        inactive_ids = [m["id"] for m in inactive_response.data["results"]]
        self.assertIn(inactive.id, inactive_ids)
        self.assertNotIn(self.membership.id, inactive_ids)

    def test_staff_sees_all_memberships(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)
        other_account = AccountFactory()
        other_persona = _active_primary_persona(account=other_account)
        other_org = OrganizationFactory(name="Other Org")
        other_membership = OrganizationMembershipFactory(
            organization=other_org,
            persona=other_persona,
        )

        response = self.client.get(reverse("societies:organization-membership-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id"] for m in response.data["results"]]
        self.assertIn(self.membership.id, ids)
        self.assertIn(other_membership.id, ids)


class OrganizationRankApiTests(TestCase):
    """Tests for the /api/societies/ranks/ endpoint."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.persona = _active_primary_persona(account=self.account)
        self.organization = OrganizationFactory(name="Rank Org")
        OrganizationMembershipFactory(organization=self.organization, persona=self.persona)

    def test_list_ranks_for_owned_organizations(self) -> None:
        """Users can list ranks for organizations they belong to."""
        rank_ids = list(self.organization.ranks.values_list("id", flat=True))
        self.assertTrue(rank_ids)

        response = self.client.get(reverse("societies:organization-rank-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [r["id"] for r in response.data["results"]]
        for rank_id in rank_ids:
            self.assertIn(rank_id, returned_ids)

    def test_list_excludes_covenant_ranks(self) -> None:
        """Rank lists exclude ranks belonging to covenant-backed organizations."""
        cov_membership = _covenant_membership(account=self.account, persona=self.persona)
        cov_rank_ids = list(cov_membership.organization.ranks.values_list("id", flat=True))
        self.assertTrue(cov_rank_ids)

        response = self.client.get(reverse("societies:organization-rank-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [r["id"] for r in response.data["results"]]
        for rank_id in cov_rank_ids:
            self.assertNotIn(rank_id, returned_ids)

    def test_staff_sees_all_non_covenant_ranks(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)
        cov_membership = _covenant_membership(account=self.account, persona=self.persona)
        other_org = OrganizationFactory(name="Other Rank Org")
        other_rank_ids = list(other_org.ranks.values_list("id", flat=True))
        cov_rank_ids = list(cov_membership.organization.ranks.values_list("id", flat=True))

        response = self.client.get(reverse("societies:organization-rank-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [r["id"] for r in response.data["results"]]
        for rank_id in other_rank_ids:
            self.assertIn(rank_id, returned_ids)
        for rank_id in cov_rank_ids:
            self.assertNotIn(rank_id, returned_ids)


class OrganizationMembershipOfferApiTests(TestCase):
    """Tests for the /api/societies/offers/ endpoint."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.persona = _active_primary_persona(account=self.account)
        self.organization = OrganizationFactory(name="Offer Org")
        OrganizationMembershipFactory(organization=self.organization, persona=self.persona)

    def test_list_offers_sent_by_user(self) -> None:
        other_persona = _active_primary_persona(account=AccountFactory())
        offer = OrganizationMembershipOfferFactory(
            organization=self.organization,
            from_persona=self.persona,
            to_persona=other_persona,
        )

        response = self.client.get(reverse("societies:organization-membership-offer-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in response.data["results"]]
        self.assertIn(offer.id, ids)

    def test_list_offers_received_by_user(self) -> None:
        other_persona = _active_primary_persona(account=AccountFactory())
        offer = OrganizationMembershipOfferFactory(
            organization=self.organization,
            from_persona=other_persona,
            to_persona=self.persona,
        )

        response = self.client.get(reverse("societies:organization-membership-offer-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in response.data["results"]]
        self.assertIn(offer.id, ids)

    def test_list_offers_visible_as_org_member(self) -> None:
        """Users can see offers sent to/from other personas within an org they belong to."""
        sender = _active_primary_persona(account=AccountFactory())
        receiver = _active_primary_persona(account=AccountFactory())
        offer = OrganizationMembershipOfferFactory(
            organization=self.organization,
            from_persona=sender,
            to_persona=receiver,
        )

        response = self.client.get(reverse("societies:organization-membership-offer-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in response.data["results"]]
        self.assertIn(offer.id, ids)

    def test_list_excludes_covenant_offers(self) -> None:
        """Offer lists exclude offers belonging to covenant-backed organizations."""
        cov_membership = _covenant_membership(account=self.account, persona=self.persona)
        other_persona = _active_primary_persona(account=AccountFactory())
        offer = OrganizationMembershipOfferFactory(
            organization=cov_membership.organization,
            from_persona=other_persona,
            to_persona=self.persona,
        )

        response = self.client.get(reverse("societies:organization-membership-offer-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in response.data["results"]]
        self.assertNotIn(offer.id, ids)

    def test_staff_sees_all_non_covenant_offers(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)
        other_account = AccountFactory()
        other_persona = _active_primary_persona(account=other_account)
        cov_membership = _covenant_membership(account=self.account, persona=self.persona)
        other_org = OrganizationFactory(name="Other Offer Org")
        regular_offer = OrganizationMembershipOfferFactory(
            organization=other_org,
            from_persona=other_persona,
            to_persona=self.persona,
        )
        covenant_offer = OrganizationMembershipOfferFactory(
            organization=cov_membership.organization,
            from_persona=other_persona,
            to_persona=self.persona,
        )

        response = self.client.get(reverse("societies:organization-membership-offer-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in response.data["results"]]
        self.assertIn(regular_offer.id, ids)
        self.assertNotIn(covenant_offer.id, ids)
