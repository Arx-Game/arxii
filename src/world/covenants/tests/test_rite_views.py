"""Tests for the CovenantRite read-only API."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.conditions.factories import ConditionTemplateFactory
from world.covenants.constants import CovenantType
from world.covenants.models import CovenantRite
from world.magic.factories import RitualFactory


class CovenantRiteViewTestCase(TestCase):
    """Base test case with authenticated API client."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.user = AccountDB.objects.create_user(
            username="riteviewtestuser",
            email="riteview@test.com",
            password="testpass123",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class CovenantRiteListTests(CovenantRiteViewTestCase):
    """Tests for GET /api/covenants/rites/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        cls.ritual_durance = RitualFactory(name="Rite View Test Ritual Durance")
        cls.ritual_battle = RitualFactory(name="Rite View Test Ritual Battle")
        cls.condition = ConditionTemplateFactory(name="Rite View Test Condition")
        cls.condition2 = ConditionTemplateFactory(name="Rite View Test Condition 2")

        cls.rite_durance = CovenantRite.objects.create(
            ritual=cls.ritual_durance,
            covenant_type=CovenantType.DURANCE,
            min_covenant_level=1,
            min_engaged_present=2,
            granted_condition=cls.condition,
            base_severity=1,
            severity_per_extra_participant=0,
        )
        cls.rite_battle = CovenantRite.objects.create(
            ritual=cls.ritual_battle,
            covenant_type=CovenantType.BATTLE,
            min_covenant_level=2,
            min_engaged_present=3,
            granted_condition=cls.condition2,
            base_severity=2,
            severity_per_extra_participant=1,
            max_severity=5,
            duration_rounds=4,
        )

    def test_list_returns_authored_rites(self) -> None:
        """GET list returns seeded rite rows."""
        response = self.client.get("/api/covenants/rites/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.rite_durance.pk, ids)
        self.assertIn(self.rite_battle.pk, ids)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/covenants/rites/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_covenant_type(self) -> None:
        """?covenant_type= narrows to rites for that type only."""
        response = self.client.get("/api/covenants/rites/", {"covenant_type": CovenantType.DURANCE})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.rite_durance.pk, ids)
        self.assertNotIn(self.rite_battle.pk, ids)

    def test_filter_by_covenant_type_battle(self) -> None:
        """?covenant_type=BATTLE returns only BATTLE rites."""
        response = self.client.get("/api/covenants/rites/", {"covenant_type": CovenantType.BATTLE})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.rite_battle.pk, ids)
        self.assertNotIn(self.rite_durance.pk, ids)

    def test_post_not_allowed(self) -> None:
        """Read-only ViewSet: POST returns 405."""
        response = self.client.post(
            "/api/covenants/rites/",
            {"ritual": self.ritual_durance.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class CovenantRiteDetailTests(CovenantRiteViewTestCase):
    """Tests for GET /api/covenants/rites/{pk}/ field exposure."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        cls.ritual = RitualFactory(name="Rite Detail Test Ritual")
        cls.condition = ConditionTemplateFactory(name="Rite Detail Test Condition")
        cls.rite = CovenantRite.objects.create(
            ritual=cls.ritual,
            covenant_type=CovenantType.DURANCE,
            min_covenant_level=3,
            min_engaged_present=2,
            granted_condition=cls.condition,
            base_severity=2,
            severity_per_extra_participant=1,
            max_severity=8,
            duration_rounds=6,
        )

    def test_detail_endpoint_returns_correct_record(self) -> None:
        """GET single rite by pk returns the correct record."""
        response = self.client.get(f"/api/covenants/rites/{self.rite.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.rite.pk)

    def test_serializer_exposes_expected_fields(self) -> None:
        """Detail endpoint exposes all expected fields."""
        response = self.client.get(f"/api/covenants/rites/{self.rite.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["ritual"], self.ritual.pk)
        self.assertEqual(data["covenant_type"], CovenantType.DURANCE)
        self.assertEqual(data["min_covenant_level"], 3)
        self.assertEqual(data["min_engaged_present"], 2)
        self.assertEqual(data["granted_condition"], self.condition.pk)
        self.assertEqual(data["base_severity"], 2)
        self.assertEqual(data["severity_per_extra_participant"], 1)
        self.assertEqual(data["max_severity"], 8)
        self.assertEqual(data["duration_rounds"], 6)

    def test_serializer_exposes_covenant_type_display(self) -> None:
        """Detail endpoint includes covenant_type_display human-readable label."""
        response = self.client.get(f"/api/covenants/rites/{self.rite.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("covenant_type_display", response.data)
        self.assertIsInstance(response.data["covenant_type_display"], str)
        self.assertGreater(len(response.data["covenant_type_display"]), 0)

    def test_nullable_fields_can_be_null(self) -> None:
        """max_severity and duration_rounds are null when not set."""
        ritual_null = RitualFactory(name="Rite Null Fields Ritual")
        condition_null = ConditionTemplateFactory(name="Rite Null Fields Condition")
        rite_null = CovenantRite.objects.create(
            ritual=ritual_null,
            covenant_type=CovenantType.DURANCE,
            min_covenant_level=1,
            min_engaged_present=2,
            granted_condition=condition_null,
            base_severity=1,
            severity_per_extra_participant=0,
            max_severity=None,
            duration_rounds=None,
        )
        response = self.client.get(f"/api/covenants/rites/{rite_null.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["max_severity"])
        self.assertIsNone(response.data["duration_rounds"])
