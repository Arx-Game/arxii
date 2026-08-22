"""DRF tests for the OrgAppeal API (#3293)."""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.societies.constants import OrgAppealState
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrgAppealFactory,
)


def _active_primary_persona(*, account):
    """Create a character sheet + active tenure and return its primary persona.

    Mirrors ``test_organization_api.py``'s helper of the same name, plus one
    fix: ``RosterTenure.related_cache_fields`` only lists ``player_data`` (and
    ``player_data.account``), not ``roster_entry`` — so creating a tenure does
    not itself invalidate ``RosterEntry.cached_tenures`` (a ``cached_property``).
    Without dropping it explicitly, ``Character.active_account`` (which
    ``OrgAppealViewSet``'s ``_active_persona_for_request`` walks through) can
    read a stale, pre-tenure empty cache. Same trap as
    ``OrgAppealActionTests.test_resolve_action_allows_staff_without_rank``.
    """
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    roster = RosterFactory()
    entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
    player_data = PlayerData.objects.create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    entry.invalidate_tenure_cache()
    return sheet.primary_persona


class OrgAppealApiTests(TestCase):
    """Journey: outsider lodges -> member signs on -> leadership grants -> petitioner reads it.

    Plus the refusal cases: an outsider reading another persona's appeal, and a
    non-privileged member trying to resolve.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        self.org = OrganizationFactory(name="Testers Guild")
        self.leader_rank = self.org.ranks.get(tier=1)

        self.petitioner_account = AccountFactory()
        self.petitioner_persona = _active_primary_persona(account=self.petitioner_account)

        self.member_account = AccountFactory()
        self.member_persona = _active_primary_persona(account=self.member_account)
        OrganizationMembershipFactory(organization=self.org, persona=self.member_persona)

        self.leader_account = AccountFactory()
        self.leader_persona = _active_primary_persona(account=self.leader_account)
        OrganizationMembershipFactory(
            organization=self.org, persona=self.leader_persona, rank=self.leader_rank
        )

        self.outsider_account = AccountFactory()
        self.outsider_persona = _active_primary_persona(account=self.outsider_account)

    def test_full_journey(self) -> None:
        # Outsider (well, the petitioner) lodges.
        self.client.force_authenticate(user=self.petitioner_account)
        lodge_response = self.client.post(
            reverse("societies:organization-appeal-list"),
            {"organization": self.org.pk, "title": "Bandits", "body": "Please send aid."},
            format="json",
        )
        self.assertEqual(lodge_response.status_code, status.HTTP_201_CREATED)
        appeal_id = lodge_response.data["id"]
        self.assertEqual(lodge_response.data["state"], OrgAppealState.OPEN)

        # A member signs on.
        self.client.force_authenticate(user=self.member_account)
        signon_response = self.client.post(
            reverse("societies:organization-appeal-signon", args=[appeal_id]),
            {"note": "I'll go."},
            format="json",
        )
        self.assertEqual(signon_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(signon_response.data["signons"]), 1)
        self.assertEqual(signon_response.data["signons"][0]["note"], "I'll go.")

        # Leadership grants it with a written answer.
        self.client.force_authenticate(user=self.leader_account)
        resolve_response = self.client.post(
            reverse("societies:organization-appeal-resolve", args=[appeal_id]),
            {"verdict": "grant", "answer": "Guards are dispatched."},
            format="json",
        )
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(resolve_response.data["state"], OrgAppealState.GRANTED)
        self.assertEqual(resolve_response.data["resolution_text"], "Guards are dispatched.")

        # The petitioner reads it.
        self.client.force_authenticate(user=self.petitioner_account)
        read_response = self.client.get(
            reverse("societies:organization-appeal-detail", args=[appeal_id])
        )
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(read_response.data["state"], OrgAppealState.GRANTED)
        self.assertEqual(read_response.data["resolution_text"], "Guards are dispatched.")

    def test_outsider_cannot_read_another_persona_s_appeal(self) -> None:
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        self.client.force_authenticate(user=self.outsider_account)

        list_response = self.client.get(reverse("societies:organization-appeal-list"))
        ids = [row["id"] for row in list_response.data["results"]]
        self.assertNotIn(appeal.pk, ids)

        detail_response = self.client.get(
            reverse("societies:organization-appeal-detail", args=[appeal.pk])
        )
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_member_can_read_org_appeal_not_their_own(self) -> None:
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        self.client.force_authenticate(user=self.member_account)

        detail_response = self.client.get(
            reverse("societies:organization-appeal-detail", args=[appeal.pk])
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

    def test_non_privileged_member_cannot_resolve(self) -> None:
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        self.client.force_authenticate(user=self.member_account)

        response = self.client.post(
            reverse("societies:organization-appeal-resolve", args=[appeal.pk]),
            {"verdict": "grant", "answer": "Sure."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        appeal.refresh_from_db()
        self.assertEqual(appeal.state, OrgAppealState.OPEN)

    def test_second_open_appeal_lodge_is_rejected(self) -> None:
        self.client.force_authenticate(user=self.petitioner_account)
        first = self.client.post(
            reverse("societies:organization-appeal-list"),
            {"organization": self.org.pk, "title": "First", "body": "Body one."},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            reverse("societies:organization-appeal-list"),
            {"organization": self.org.pk, "title": "Second", "body": "Body two."},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_petitioner_withdraws_own_appeal(self) -> None:
        self.client.force_authenticate(user=self.petitioner_account)
        appeal = OrgAppealFactory(organization=self.org, petitioner_persona=self.petitioner_persona)
        response = self.client.post(
            reverse("societies:organization-appeal-withdraw", args=[appeal.pk]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], OrgAppealState.WITHDRAWN)
