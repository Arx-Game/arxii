"""API tests for directed-offer summonses (#2050).

Drives the create/list flow through HTTP. The respond action is tested at
the service level (test_summons.py) since it requires a live Evennia puppet
session which unit tests don't spin up.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.missions.factories import MissionNodeFactory
from world.npc_services.constants import OfferKind, SummonsStatus
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCServiceOfferFactory,
)
from world.npc_services.summons import create_summons
from world.scenes.factories import PersonaFactory

SUMMONS_URL = "/api/npc-services/summons/"


def _staff(username="staff"):
    """A staff account."""
    return AccountFactory(username=username, is_staff=True)


def _mission_offer():
    """A MISSION-kind offer with details + entry node."""
    offer = NPCServiceOfferFactory(kind=OfferKind.MISSION)
    details = MissionOfferDetailsFactory(offer=offer)
    MissionNodeFactory(template=details.mission_template, is_entry=True)
    return offer


class CreateSummonsAPITests(TestCase):
    def setUp(self):
        self.staff = _staff()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.offer = _mission_offer()
        self.target_persona = PersonaFactory()

    def test_staff_can_create_summons(self):
        """Staff POST creates a PENDING summons."""
        resp = self.client.post(
            SUMMONS_URL,
            {
                "offer_id": self.offer.pk,
                "target_persona_id": self.target_persona.pk,
                "message": "Come at once.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], SummonsStatus.PENDING)
        self.assertEqual(resp.data["message"], "Come at once.")

    def test_non_staff_cannot_create(self):
        """Non-staff players get 403 on create."""
        account = AccountFactory(username="nonstaff")
        client = APIClient()
        client.force_authenticate(account)
        resp = client.post(
            SUMMONS_URL,
            {"offer_id": self.offer.pk, "target_persona_id": self.target_persona.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_rejects_non_mission_offer(self):
        """Non-MISSION offers are rejected."""
        offer = NPCServiceOfferFactory(kind=OfferKind.PERMIT)
        resp = self.client.post(
            SUMMONS_URL,
            {"offer_id": offer.pk, "target_persona_id": self.target_persona.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_with_expiry(self):
        """A summons with an expiry is stored."""
        from datetime import timedelta

        from django.utils import timezone

        deadline = (timezone.now() + timedelta(hours=24)).isoformat()
        resp = self.client.post(
            SUMMONS_URL,
            {
                "offer_id": self.offer.pk,
                "target_persona_id": self.target_persona.pk,
                "expires_at": deadline,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(resp.data["expires_at"])


class ListSummonsAPITests(TestCase):
    def setUp(self):
        self.staff = _staff()
        self.offer = _mission_offer()
        self.persona = PersonaFactory()
        # Create a summons directly via the service.
        self.summons = create_summons(self.offer, self.persona, message="Test.")

    def test_staff_lists_all_summons(self):
        """Staff sees all summonses."""
        client = APIClient()
        client.force_authenticate(self.staff)
        resp = client.get(SUMMONS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["message"], "Test.")

    def test_non_staff_empty_list_without_puppet(self):
        """Non-staff without a puppet sees an empty list."""
        account = AccountFactory(username="player1")
        client = APIClient()
        client.force_authenticate(account)
        resp = client.get(SUMMONS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 0)


class RetrieveSummonsAPITests(TestCase):
    def setUp(self):
        self.staff = _staff()
        self.offer = _mission_offer()
        self.persona = PersonaFactory()
        self.summons = create_summons(self.offer, self.persona, message="Come.")

    def test_staff_can_retrieve_summons(self):
        """Staff can retrieve a single summons."""
        client = APIClient()
        client.force_authenticate(self.staff)
        resp = client.get(f"{SUMMONS_URL}{self.summons.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["message"], "Come.")
        self.assertEqual(resp.data["role_name"], self.offer.role.name)
