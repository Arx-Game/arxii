"""API tests for the NPCStanding staff CRUD viewset.

Relocated + reshaped from the old `world.missions` standing API tests —
the model is now per-(PC persona, NPC persona) and only carries
affection / interaction-summary. Cooldown lives on `OfferCooldown`
(see test_api_offer_cooldowns.py).
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.npc_services.factories import NPCStandingFactory
from world.scenes.factories import PersonaFactory


def _staff_account(name: str):
    """Helper: an Account flagged is_staff for IsAdminUser checks."""
    account = AccountFactory(username=name)
    account.is_staff = True
    account.save(update_fields=["is_staff"])
    return account


class NPCStandingViewSetTests(TestCase):
    URL = "/api/npc-services/standings/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _staff_account("staff-npc-std")
        cls.pc_persona = PersonaFactory()
        cls.npc_persona = PersonaFactory()
        cls.standing = NPCStandingFactory(
            persona=cls.pc_persona, npc_persona=cls.npc_persona, affection=42
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_persona(self) -> None:
        response = self.client.get(self.URL, {"persona": self.pc_persona.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_list_filters_by_npc_persona(self) -> None:
        response = self.client.get(self.URL, {"npc_persona": self.npc_persona.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_patch_adjusts_affection(self) -> None:
        response = self.client.patch(
            f"{self.URL}{self.standing.pk}/",
            {"affection": -10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["affection"], -10)

    def test_create_new_standing(self) -> None:
        other_pc = PersonaFactory()
        response = self.client.post(
            self.URL,
            {
                "persona": other_pc.pk,
                "npc_persona": self.npc_persona.pk,
                "affection": 0,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_anonymous_blocked(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(self.URL)
        # DRF returns 403 when no auth credentials are sent and no
        # WWW-Authenticate scheme would yield 401 — the project doesn't
        # configure session/basic auth that emits 401, so 403 is correct.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
