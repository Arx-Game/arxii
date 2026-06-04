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
from world.items.services.equip import equip_item
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
        from evennia_extensions.factories import AccountFactory, CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import FacetFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()
        cls.quality = QualityTierFactory(name="ItemFacetViewQuality")
        cls.facet_a = FacetFactory(name="ViewFacetA")
        cls.facet_b = FacetFactory(name="ViewFacetB")
        cls.facet_c = FacetFactory(name="ViewFacetC")

        # #684: ownership is body-keyed. Wire each account to a character +
        # sheet via an active RosterTenure so the permission walk
        # (RosterEntry.objects.for_account) finds the entry.
        cls.owner = AccountFactory(username="facet_view_owner")
        cls.owner_char = CharacterFactory(db_key="facet_view_owner_char")
        cls.owner_sheet = CharacterSheetFactory(character=cls.owner_char)
        owner_entry = RosterEntryFactory(character_sheet=cls.owner_sheet)
        RosterTenureFactory(
            roster_entry=owner_entry,
            player_data=PlayerDataFactory(account=cls.owner),
        )
        cls.non_owner = AccountFactory(username="facet_view_nonowner")
        cls.non_owner_char = CharacterFactory(db_key="facet_view_nonowner_char")
        cls.non_owner_sheet = CharacterSheetFactory(character=cls.non_owner_char)
        non_owner_entry = RosterEntryFactory(character_sheet=cls.non_owner_sheet)
        RosterTenureFactory(
            roster_entry=non_owner_entry,
            player_data=PlayerDataFactory(account=cls.non_owner),
        )

        cls.template_cap2 = ItemTemplateFactory(name="FacetView Cap2 Template", facet_capacity=2)
        cls.template_cap1 = ItemTemplateFactory(name="FacetView Cap1 Template", facet_capacity=1)

        cls.item_owner = ItemInstanceFactory(
            template=cls.template_cap2, holder_character_sheet=cls.owner_sheet
        )
        cls.item_other = ItemInstanceFactory(
            template=cls.template_cap2, holder_character_sheet=cls.non_owner_sheet
        )
        cls.item_cap1 = ItemInstanceFactory(
            template=cls.template_cap1, holder_character_sheet=cls.owner_sheet
        )
        # End-of-setup hook: any test that authenticates as cls.owner needs
        # the items' holder relation primed (the select_related path through
        # holder_character_sheet→character is used by the permission walk).

    def setUp(self) -> None:
        super().setUp()
        # Authenticate as the item owner by default.
        self.client.force_authenticate(user=self.owner)
        # Test pollution guard: prior tests leave stale prefetch caches on the
        # identity-mapped ItemInstances. Flushing the model's instance cache
        # forces a fresh instance on the next ``.get(pk=...)`` so the view's
        # prefetch isn't shadowed by stale state on the test class's instances.
        from world.items.models import ItemFacet, ItemInstance

        ItemFacet.flush_instance_cache()
        ItemInstance.flush_instance_cache()

    def test_list_returns_facets(self) -> None:
        """GET list includes an attached ItemFacet for an owned item."""
        row = attach_facet_to_item(
            crafter=self.owner,
            item_instance=self.item_owner,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        response = self.client.get(f"/api/items/item-facets/?item_instance={self.item_owner.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(row.pk, result_ids)

    def test_list_requires_item_instance_param(self) -> None:
        """GET without ?item_instance returns 400."""
        response = self.client.get("/api/items/item-facets/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_non_owner_returns_404(self) -> None:
        """Non-owner asking for another user's item's facets gets 404 (no leak)."""
        attach_facet_to_item(
            crafter=self.non_owner,
            item_instance=self.item_other,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        # Authenticated as owner — but item_other belongs to non_owner.
        response = self.client.get(f"/api/items/item-facets/?item_instance={self.item_other.pk}")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

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


class EquippedItemViewTests(ItemViewTestCase):
    """Tests for /api/items/equipped-items/ endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()

        # Character + sheet + active tenure for the default user.
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )

        # A second character/sheet for non-owner tests.
        cls.other_sheet = CharacterSheetFactory()
        cls.other_character = cls.other_sheet.character
        cls.other_roster_entry = RosterEntryFactory(character_sheet=cls.other_sheet)
        cls.other_account = AccountFactory(username="equipped_view_other")
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            roster_entry=cls.other_roster_entry,
            player_data=cls.other_player_data,
            end_date=None,
        )

        # Template with a slot (TORSO/BASE).
        cls.template = ItemTemplateFactory(name="EquippedView Tunic")
        TemplateSlot.objects.create(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # Template without any slots (for SlotIncompatible tests).
        cls.slotless_template = ItemTemplateFactory(name="EquippedView Slotless")

    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(user=self.user)
        # Test pollution guard: prior tests that bypass unequip_item with
        # direct ``row.delete()`` leave stale entries in the equipped_items
        # handler cache. Direct .invalidate() on self.character resets that
        # character's handler. We also flush EquippedItem instance cache so
        # any stale (pk=None) instances aren't returned by later filter().
        from evennia.objects.models import ObjectDB

        from world.items.models import EquippedItem

        EquippedItem.flush_instance_cache()
        # Invalidate via the same path the view uses (ObjectDB.objects.get)
        # so handler state matches across test and view code paths.
        char = ObjectDB.objects.get(pk=self.character.pk)
        char.equipped_items.invalidate()
        other = ObjectDB.objects.get(pk=self.other_character.pk)
        other.equipped_items.invalidate()

    # ------------------------------------------------------------------
    # GET list
    # ------------------------------------------------------------------

    def test_list_returns_equipped(self) -> None:
        """GET list includes an EquippedItem created via service."""
        instance = ItemInstanceFactory(template=self.template)
        row = equip_item(
            character_sheet=self.sheet,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        response = self.client.get(f"/api/items/equipped-items/?character={self.character.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(row.pk, result_ids)
        # Clean up so other tests don't see this row.
        row.delete()

    def test_list_requires_character_param(self) -> None:
        """GET list without ?character returns 400."""
        response = self.client.get("/api/items/equipped-items/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_other_user_character_returns_404(self) -> None:
        """Non-staff cannot list a character they don't play."""
        response = self.client.get(
            f"/api/items/equipped-items/?character={self.other_character.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_staff_can_view_any_character(self) -> None:
        """Staff bypass: can list any character's equipped items."""
        self.user.is_staff = True
        self.user.save()
        instance = ItemInstanceFactory(template=self.template)
        row = equip_item(
            character_sheet=self.other_sheet,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        response = self.client.get(
            f"/api/items/equipped-items/?character={self.other_character.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(row.pk, result_ids)
        row.delete()
        self.user.is_staff = False
        self.user.save()

    def test_filter_by_character(self) -> None:
        """GET ?character=<pk> filters to only that character's equipped items."""
        instance_a = ItemInstanceFactory(template=self.template)
        row_a = equip_item(
            character_sheet=self.sheet,
            item_instance=instance_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        # Equip on the other character's template too (same slot).
        other_template = ItemTemplateFactory(name="EquippedView Filter OtherTunic")
        TemplateSlot.objects.create(
            template=other_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        instance_b = ItemInstanceFactory(template=other_template)
        row_b = equip_item(
            character_sheet=self.other_sheet,
            item_instance=instance_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        response = self.client.get(f"/api/items/equipped-items/?character={self.character.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(row_a.pk, result_ids)
        self.assertNotIn(row_b.pk, result_ids)
        row_a.delete()
        row_b.delete()

    # ------------------------------------------------------------------
    # Auth / method guards
    # ------------------------------------------------------------------

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests are rejected with 403."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/items/equipped-items/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_method_not_allowed(self) -> None:
        """POST is disabled — equip flows through the action dispatcher."""
        response = self.client.post(
            "/api/items/equipped-items/",
            {
                "character_sheet": self.sheet.pk,
                "item_instance": ItemInstanceFactory(template=self.template).pk,
                "body_region": BodyRegion.TORSO,
                "equipment_layer": EquipmentLayer.BASE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_method_not_allowed(self) -> None:
        """DELETE is disabled — unequip flows through the action dispatcher."""
        instance = ItemInstanceFactory(template=self.template)
        row = equip_item(
            character_sheet=self.sheet,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        response = self.client.delete(f"/api/items/equipped-items/{row.pk}/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        row.delete()

    def test_put_method_not_allowed(self) -> None:
        """PUT and PATCH are disabled — read-only viewset."""
        instance = ItemInstanceFactory(template=self.template)
        row = equip_item(
            character_sheet=self.sheet,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        response = self.client.put(
            f"/api/items/equipped-items/{row.pk}/",
            {
                "character_sheet": self.sheet.pk,
                "item_instance": instance.pk,
                "body_region": BodyRegion.TORSO,
                "equipment_layer": EquipmentLayer.BASE,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.patch(f"/api/items/equipped-items/{row.pk}/", {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        row.delete()
