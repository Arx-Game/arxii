"""Tests for item API views."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    InteractionTypeFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.models import TemplateInteraction, TemplateSlot


class ItemViewTestCase(TestCase):
    """Base test case with authenticated API client."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.user = AccountDB.objects.create_user(
            username="itemtestuser",
            email="items@test.com",
            password="testpass123",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class QualityTierViewTests(ItemViewTestCase):
    """Tests for GET /api/items/quality-tiers/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.tier = QualityTierFactory(name="Fine", sort_order=3)

    def test_list(self) -> None:
        """Returns quality tiers."""
        response = self.client.get("/api/items/quality-tiers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [t["name"] for t in response.data]
        self.assertIn("Fine", names)

    def test_detail(self) -> None:
        """Returns single quality tier."""
        response = self.client.get(f"/api/items/quality-tiers/{self.tier.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Fine")
        self.assertIn("color_hex", response.data)
        self.assertIn("stat_multiplier", response.data)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/items/quality-tiers/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InteractionTypeViewTests(ItemViewTestCase):
    """Tests for GET /api/items/interaction-types/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.interaction = InteractionTypeFactory(name="eat", label="Eat")

    def test_list(self) -> None:
        """Returns interaction types."""
        response = self.client.get("/api/items/interaction-types/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [i["name"] for i in response.data]
        self.assertIn("eat", names)

    def test_detail(self) -> None:
        """Returns single interaction type."""
        response = self.client.get(f"/api/items/interaction-types/{self.interaction.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["label"], "Eat")


class ItemTemplateViewTests(ItemViewTestCase):
    """Tests for GET /api/items/templates/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.eat = InteractionTypeFactory(name="eat", label="Eat")
        cls.template = ItemTemplateFactory(name="Iron Longsword")
        TemplateInteraction.objects.create(
            template=cls.template,
            interaction_type=cls.eat,
        )

    def test_list(self) -> None:
        """Returns item templates."""
        response = self.client.get("/api/items/templates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [t["name"] for t in response.data["results"]]
        self.assertIn("Iron Longsword", names)

    def test_list_excludes_inactive(self) -> None:
        """Inactive templates are excluded by default."""
        ItemTemplateFactory(name="Deprecated Sword", is_active=False)
        response = self.client.get("/api/items/templates/")
        names = [t["name"] for t in response.data["results"]]
        self.assertNotIn("Deprecated Sword", names)

    def test_detail_includes_slots_and_interactions(self) -> None:
        """Detail view includes equipment slots and interaction types."""
        TemplateSlot.objects.create(
            template=self.template,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        response = self.client.get(f"/api/items/templates/{self.template.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("slots", response.data)
        self.assertIn("interactions", response.data)
        self.assertEqual(len(response.data["slots"]), 1)
        self.assertEqual(len(response.data["interactions"]), 1)
