"""API tests for ``MissionOfferDetailsViewSet`` (#728).

Mirrors the shape of ``test_api_standings.py``. Unblocks the
Mission Studio FE editor (#728) by providing the
``/api/npc-services/mission-details/`` CRUD surface.

Covers the role-mirror invariant from #686 Phase 6: the model's
``save()`` mirrors ``role`` from ``offer.role`` on every write, so the
serializer marks ``role`` read-only and the
``(role, mission_template)`` uniqueness is enforced at the DB level
without the FE ever passing role.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.missions.factories import MissionTemplateFactory
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
)
from world.npc_services.models import MissionOfferDetails


def _staff_account(name: str):
    """Helper: an Account flagged is_staff for IsAdminUser checks."""
    account = AccountFactory(username=name)
    account.is_staff = True
    account.save(update_fields=["is_staff"])
    return account


class MissionOfferDetailsViewSetTests(TestCase):
    URL = "/api/npc-services/mission-details/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _staff_account("staff-mod-api")
        cls.role = NPCRoleFactory(name="mod-test-role")
        cls.template = MissionTemplateFactory(name="mod-test-template")

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _make_mission_offer(self):
        return NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.MISSION,
            label="mod-test-offer",
        )

    def test_anonymous_denied(self) -> None:
        client = APIClient()
        response = client.get(self.URL)
        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_non_staff_denied(self) -> None:
        non_staff = AccountFactory(username="non-staff-mod")
        self.client.force_authenticate(non_staff)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_returns_existing_details(self) -> None:
        offer = self._make_mission_offer()
        MissionOfferDetailsFactory(offer=offer, mission_template=self.template)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_role_scopes_results(self) -> None:
        """?role= scopes to one role's details (the FE editor relies on it)."""
        MissionOfferDetailsFactory(offer=self._make_mission_offer(), mission_template=self.template)
        other_role = NPCRoleFactory(name="other-role")
        other_offer = NPCServiceOfferFactory(
            role=other_role, kind=OfferKind.MISSION, label="other-offer"
        )
        MissionOfferDetailsFactory(
            offer=other_offer, mission_template=MissionTemplateFactory(name="other-template")
        )

        response = self.client.get(self.URL, {"role": self.role.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["role"], self.role.pk)

    def test_create_round_trip(self) -> None:
        offer = self._make_mission_offer()
        response = self.client.post(
            self.URL,
            data={
                "offer": offer.pk,
                "mission_template": self.template.pk,
                "weight": 3,
                "requirements_override": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Role is denormalized from offer.role on save() and is
        # read-only in the API; the response echoes it for the FE.
        self.assertEqual(response.data["role"], self.role.pk)

    def test_create_ignores_client_supplied_role(self) -> None:
        """The serializer's read_only role means a client-supplied value
        is silently dropped; the model's save() mirror sets it from
        offer.role. Verifies the mirror invariant is enforced at the
        write boundary, not just the model layer."""
        offer = self._make_mission_offer()
        other_role = NPCRoleFactory(name="mod-other-role")
        response = self.client.post(
            self.URL,
            data={
                "offer": offer.pk,
                "mission_template": self.template.pk,
                "role": other_role.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Stored role is offer.role, not the client-supplied other_role.
        details = MissionOfferDetails.objects.get(pk=response.data["id"])
        self.assertEqual(details.role_id, self.role.pk)

    def test_patch_updates_mission_specific_fields(self) -> None:
        offer = self._make_mission_offer()
        details = MissionOfferDetailsFactory(offer=offer, mission_template=self.template)
        response = self.client.patch(
            f"{self.URL}{details.pk}/",
            data={"weight": 9, "requirements_override": {"op": "AND", "of": []}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        details.refresh_from_db()
        self.assertEqual(details.weight, 9)
        self.assertEqual(details.requirements_override, {"op": "AND", "of": []})

    def test_delete_removes_row(self) -> None:
        offer = self._make_mission_offer()
        details = MissionOfferDetailsFactory(offer=offer, mission_template=self.template)
        response = self.client.delete(f"{self.URL}{details.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MissionOfferDetails.objects.filter(pk=details.pk).exists())
