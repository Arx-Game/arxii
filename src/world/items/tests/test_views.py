"""Tests for item API views."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    InteractionTypeFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.models import ItemFacet, TemplateInteraction, TemplateSlot
from world.items.services.facets import attach_facet_to_item


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


class ItemFacetViewTests(ItemViewTestCase):
    """Tests for /api/items/item-facets/ endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.magic.factories import FacetFactory

        super().setUpTestData()
        cls.quality = QualityTierFactory(name="ItemFacetViewQuality")
        cls.facet_a = FacetFactory(name="ViewFacetA")
        cls.facet_b = FacetFactory(name="ViewFacetB")
        cls.facet_c = FacetFactory(name="ViewFacetC")

        # An account that owns items (used as the authenticated user in most tests).
        cls.owner = AccountFactory(username="facet_view_owner")
        # A second account that does NOT own the items.
        cls.non_owner = AccountFactory(username="facet_view_nonowner")

        cls.template_cap2 = ItemTemplateFactory(name="FacetView Cap2 Template", facet_capacity=2)
        cls.template_cap1 = ItemTemplateFactory(name="FacetView Cap1 Template", facet_capacity=1)

        cls.item_owner = ItemInstanceFactory(template=cls.template_cap2, owner=cls.owner)
        cls.item_other = ItemInstanceFactory(template=cls.template_cap2, owner=cls.non_owner)
        cls.item_cap1 = ItemInstanceFactory(template=cls.template_cap1, owner=cls.owner)

    def setUp(self) -> None:
        super().setUp()
        # Authenticate as the item owner by default.
        self.client.force_authenticate(user=self.owner)

    def test_list_returns_facets(self) -> None:
        """GET list includes an attached ItemFacet."""
        row = attach_facet_to_item(
            crafter=self.owner,
            item_instance=self.item_owner,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        response = self.client.get("/api/items/item-facets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(row.pk, result_ids)

    def test_filter_by_item_instance(self) -> None:
        """GET ?item_instance=<pk> returns only that item's facets."""
        attach_facet_to_item(
            crafter=self.owner,
            item_instance=self.item_owner,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        attach_facet_to_item(
            crafter=self.non_owner,
            item_instance=self.item_other,
            facet=self.facet_b,
            attachment_quality_tier=self.quality,
        )
        response = self.client.get(f"/api/items/item-facets/?item_instance={self.item_owner.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(item["item_instance"], self.item_owner.pk)

    def test_post_create_calls_service(self) -> None:
        """POST creates an ItemFacet via the service; applied_by_account is set."""
        response = self.client.post(
            "/api/items/item-facets/",
            {
                "item_instance": self.item_owner.pk,
                "facet": self.facet_a.pk,
                "attachment_quality_tier": self.quality.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        row = ItemFacet.objects.get(item_instance=self.item_owner, facet=self.facet_a)
        self.assertEqual(row.applied_by_account_id, self.owner.pk)

    def test_post_rejects_non_owner(self) -> None:
        """Non-owner POST to attach a facet to someone else's item is rejected with 403."""
        self.client.force_authenticate(user=self.non_owner)
        response = self.client.post(
            "/api/items/item-facets/",
            {
                "item_instance": self.item_owner.pk,
                "facet": self.facet_a.pk,
                "attachment_quality_tier": self.quality.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_facet_already_attached_returns_400(self) -> None:
        """POST same facet on same item a second time returns 400 with user_message."""
        attach_facet_to_item(
            crafter=self.owner,
            item_instance=self.item_owner,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        response = self.client.post(
            "/api/items/item-facets/",
            {
                "item_instance": self.item_owner.pk,
                "facet": self.facet_a.pk,
                "attachment_quality_tier": self.quality.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("That facet is already attached to this item.", str(response.data))

    def test_post_capacity_exceeded_returns_400(self) -> None:
        """POST a second facet on a cap-1 item returns 400."""
        attach_facet_to_item(
            crafter=self.owner,
            item_instance=self.item_cap1,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        response = self.client.post(
            "/api/items/item-facets/",
            {
                "item_instance": self.item_cap1.pk,
                "facet": self.facet_b.pk,
                "attachment_quality_tier": self.quality.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This item has no remaining facet slots.", str(response.data))

    def test_delete_calls_remove_service(self) -> None:
        """DELETE removes the ItemFacet row via the service."""
        row = attach_facet_to_item(
            crafter=self.owner,
            item_instance=self.item_owner,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        response = self.client.delete(f"/api/items/item-facets/{row.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ItemFacet.objects.filter(pk=row.pk).exists())

    def test_delete_rejects_non_owner(self) -> None:
        """Non-owner DELETE is rejected with 403."""
        row = attach_facet_to_item(
            crafter=self.non_owner,
            item_instance=self.item_other,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        # owner does not own item_other
        response = self.client.delete(f"/api/items/item-facets/{row.pk}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests are rejected with 403."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/items/item-facets/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_method_not_allowed(self) -> None:
        """PUT and PATCH are disabled — model has no editable fields after create."""
        row = ItemFacetFactory(
            item_instance=self.item_owner,
            facet=self.facet_c,
            attachment_quality_tier=self.quality,
        )
        response = self.client.put(
            f"/api/items/item-facets/{row.pk}/",
            {
                "item_instance": self.item_owner.pk,
                "facet": self.facet_c.pk,
                "attachment_quality_tier": self.quality.pk,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.patch(f"/api/items/item-facets/{row.pk}/", {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
