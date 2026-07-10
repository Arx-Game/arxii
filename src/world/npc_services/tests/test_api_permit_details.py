"""API tests for the widened ``PermitOfferDetailsSerializer`` (#1684).

Closes #728's residual: the permit-details endpoint existed but exposed only
``["id", "offer"]`` — the real authoring fields (building_kind FK, ward M2M,
size cap, permit cost) weren't writable over the API. Mirrors
``test_api_mission_details.py``'s shape.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingKindFactory
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    PermitOfferDetailsFactory,
)
from world.npc_services.models import PermitOfferDetails


def _staff_account(name: str):
    account = AccountFactory(username=name)
    account.is_staff = True
    account.save(update_fields=["is_staff"])
    return account


class PermitOfferDetailsViewSetTests(TestCase):
    URL = "/api/npc-services/permit-details/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _staff_account("staff-pod-api")
        cls.role = NPCRoleFactory(name="pod-test-role")
        cls.building_kind = BuildingKindFactory()
        cls.ward_a = AreaFactory()
        cls.ward_b = AreaFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _make_permit_offer(self):
        return NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.PERMIT,
            label="pod-test-offer",
        )

    def test_create_with_full_fields(self) -> None:
        offer = self._make_permit_offer()
        response = self.client.post(
            self.URL,
            {
                "offer": offer.pk,
                "building_kind": self.building_kind.pk,
                "default_approved_wards": [self.ward_a.pk, self.ward_b.pk],
                "default_max_target_size": 25,
                "permit_cost_currency": 5000,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        details = PermitOfferDetails.objects.get(offer=offer)
        self.assertEqual(details.building_kind, self.building_kind)
        self.assertEqual(
            set(details.default_approved_wards.values_list("pk", flat=True)),
            {self.ward_a.pk, self.ward_b.pk},
        )
        self.assertEqual(details.default_max_target_size, 25)
        self.assertEqual(details.permit_cost_currency, 5000)

    def test_patch_updates_fk_and_m2m(self) -> None:
        details = PermitOfferDetailsFactory(offer=self._make_permit_offer())
        response = self.client.patch(
            f"{self.URL}{details.pk}/",
            {
                "building_kind": self.building_kind.pk,
                "default_approved_wards": [self.ward_b.pk],
                "permit_cost_currency": 750,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        details.refresh_from_db()
        self.assertEqual(details.building_kind, self.building_kind)
        self.assertEqual(
            list(details.default_approved_wards.values_list("pk", flat=True)),
            [self.ward_b.pk],
        )
        self.assertEqual(details.permit_cost_currency, 750)

    def test_read_exposes_all_fields(self) -> None:
        details = PermitOfferDetailsFactory(offer=self._make_permit_offer())
        response = self.client.get(f"{self.URL}{details.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for field in (
            "offer",
            "building_kind",
            "default_approved_wards",
            "default_max_target_size",
            "permit_cost_currency",
        ):
            self.assertIn(field, response.data)

    def test_role_filter_walks_offer_fk(self) -> None:
        mine = PermitOfferDetailsFactory(offer=self._make_permit_offer())
        other_role = NPCRoleFactory(name="pod-other-role")
        PermitOfferDetailsFactory(
            offer=NPCServiceOfferFactory(
                role=other_role, kind=OfferKind.PERMIT, label="pod-other-offer"
            )
        )
        response = self.client.get(f"{self.URL}?role={self.role.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data["results"]], [mine.pk])

    def test_anonymous_denied(self) -> None:
        client = APIClient()
        response = client.get(self.URL)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
