"""Ceremony API tests (#2289) — including the twisted-rite leak rule."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.ceremonies.factories import CeremonyFactory
from world.ceremonies.serializers import CeremonySerializer
from world.worship.factories import WorshippedBeingFactory


class CeremonyApiTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_serializer_never_exposes_true_being_of_twisted_rite(self) -> None:
        dark = WorshippedBeingFactory(name="The Hidden Flame Test")
        public = WorshippedBeingFactory(name="The Public Face Test")
        twisted = CeremonyFactory(being=dark, presented_being=public)
        payload = CeremonySerializer(twisted).data
        self.assertEqual(payload["presented_being_name"], public.name)
        self.assertNotIn(dark.name, str(payload))
        self.assertNotIn("being_id", payload)

    def test_list_filters_by_status(self) -> None:
        CeremonyFactory()
        response = self.client.get("/api/ceremonies/ceremonies/", {"status": "open"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_beings_catalog_lists_active_only(self) -> None:
        WorshippedBeingFactory(name="Active God Test")
        WorshippedBeingFactory(name="Retired God Test", is_active=False)
        response = self.client.get("/api/worship/beings/")
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn("Active God Test", names)
        self.assertNotIn("Retired God Test", names)
