"""Tests for OutfitViewSet and OutfitSlotViewSet REST endpoints."""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    OutfitSlotFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem, ItemInstance, Outfit, OutfitSlot
from world.items.services.equip import equip_item
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class _OutfitViewSetSetupMixin:
    """Shared setUp for outfit view tests.

    Builds: account A playing sheet A, account B playing sheet B, a wardrobe
    instance, and templates with TORSO/BASE and LEFT_HAND/BASE slots.
    """

    def setUp(self) -> None:
        # Shared room so the wardrobe is in reach of character A.
        self.room = ObjectDBFactory(
            db_key="OutfitViewRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        # Account A → plays character/sheet A.
        self.account_a = AccountFactory(username="outfit_view_account_a")
        self.character_a = CharacterFactory(db_key="OutfitViewCharA", location=self.room)
        self.sheet_a = CharacterSheetFactory(character=self.character_a)
        self.entry_a = RosterEntryFactory(character_sheet=self.sheet_a)
        self.player_data_a = PlayerDataFactory(account=self.account_a)
        self.tenure_a = RosterTenureFactory(
            roster_entry=self.entry_a,
            player_data=self.player_data_a,
            end_date=None,
        )

        # Account B → plays character/sheet B (used for non-owner tests).
        self.account_b = AccountFactory(username="outfit_view_account_b")
        self.character_b = CharacterFactory(db_key="OutfitViewCharB", location=self.room)
        self.sheet_b = CharacterSheetFactory(character=self.character_b)
        self.entry_b = RosterEntryFactory(character_sheet=self.sheet_b)
        self.player_data_b = PlayerDataFactory(account=self.account_b)
        self.tenure_b = RosterTenureFactory(
            roster_entry=self.entry_b,
            player_data=self.player_data_b,
            end_date=None,
        )

        # Wardrobe instance for sheet A — placed in the shared room so reach
        # validation in save_outfit passes for character A.
        self.wardrobe_template = ItemTemplateFactory(
            name="OutfitViewWardrobeA",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="OutfitViewWardrobeAObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = self.room
        wardrobe_obj.save()
        self.wardrobe = ItemInstanceFactory(
            template=self.wardrobe_template,
            game_object=wardrobe_obj,
        )

        # Bind characters to their accounts so item-ownership checks resolve.
        self.character_a.db_account = self.account_a
        self.character_a.save()
        self.character_b.db_account = self.account_b
        self.character_b.save()

        # Shirt template + instance (TORSO/BASE) — owned by account A.
        self.shirt_template = ItemTemplateFactory(name="OutfitViewShirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        shirt_obj = ObjectDBFactory(
            db_key="OutfitViewShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = self.character_a
        shirt_obj.save()
        self.shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=shirt_obj,
            owner=self.account_a,
        )

        # Glove template + instance (LEFT_HAND/BASE) — owned by account A.
        self.glove_template = ItemTemplateFactory(name="OutfitViewGlove")
        TemplateSlotFactory(
            template=self.glove_template,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        glove_obj = ObjectDBFactory(
            db_key="OutfitViewGloveObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        glove_obj.location = self.character_a
        glove_obj.save()
        self.glove = ItemInstanceFactory(
            template=self.glove_template,
            game_object=glove_obj,
            owner=self.account_a,
        )

        # A slotless template (for SlotIncompatible tests) — owned by account A.
        self.slotless_template = ItemTemplateFactory(name="OutfitViewSlotless")
        slotless_obj = ObjectDBFactory(
            db_key="OutfitViewSlotlessObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        slotless_obj.location = self.character_a
        slotless_obj.save()
        self.slotless_item = ItemInstanceFactory(
            template=self.slotless_template,
            game_object=slotless_obj,
            owner=self.account_a,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.account_a)


class OutfitViewSetTests(_OutfitViewSetSetupMixin, TestCase):
    """Tests for /api/items/outfits/."""

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def test_list_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/items/outfits/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    # ------------------------------------------------------------------
    # GET list / retrieve
    # ------------------------------------------------------------------

    def test_list_returns_own_outfits(self) -> None:
        """GET list returns outfits whose character_sheet belongs to the request user."""
        own_outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="OwnLook",
        )
        other_outfit = OutfitFactory(
            character_sheet=self.sheet_b,
            wardrobe=self.wardrobe,
            name="OtherLook",
        )

        response = self.client.get(f"/api/items/outfits/?character_sheet={self.sheet_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(own_outfit.pk, result_ids)
        self.assertNotIn(other_outfit.pk, result_ids)

    def test_list_scoped_to_user_even_with_other_sheet_filter(self) -> None:
        """Filtering by ?character_sheet=<other> still returns nothing for non-staff.

        Regression test for the queryset scope: the filter is a refinement on
        top of the scoped queryset, not an override. A user passing another
        character's sheet id sees an empty list, not a 403 — the items are
        simply not in their queryset.
        """
        OutfitFactory(
            character_sheet=self.sheet_b,
            wardrobe=self.wardrobe,
            name="OtherSheetLook",
        )

        response = self.client.get(f"/api/items/outfits/?character_sheet={self.sheet_b.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])

    def test_retrieve_other_users_outfit_returns_404(self) -> None:
        """GET detail on another user's outfit is hidden from the queryset (404)."""
        other_outfit = OutfitFactory(
            character_sheet=self.sheet_b,
            wardrobe=self.wardrobe,
            name="OtherUserOutfit",
        )

        response = self.client.get(f"/api/items/outfits/{other_outfit.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_sees_all_outfits(self) -> None:
        """Staff users bypass the per-account scope on the outfit list."""
        staff = AccountFactory(username="outfit_view_staff", is_staff=True)
        OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="StaffSeesAOutfit",
        )
        OutfitFactory(
            character_sheet=self.sheet_b,
            wardrobe=self.wardrobe,
            name="StaffSeesBOutfit",
        )
        self.client.force_authenticate(user=staff)

        response = self.client.get("/api/items/outfits/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {r["name"] for r in response.data["results"]}
        self.assertIn("StaffSeesAOutfit", names)
        self.assertIn("StaffSeesBOutfit", names)

    def test_retrieve_returns_outfit_with_slots(self) -> None:
        """GET detail includes nested slots with item details."""
        outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="DetailLook",
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=self.glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        response = self.client.get(f"/api/items/outfits/{outfit.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "DetailLook")
        slots = response.data["slots"]
        self.assertEqual(len(slots), 2)
        slot_item_ids = {s["item_instance"]["id"] for s in slots}
        self.assertEqual(slot_item_ids, {self.shirt.pk, self.glove.pk})

    # ------------------------------------------------------------------
    # POST create
    # ------------------------------------------------------------------

    def test_create_calls_save_outfit_service(self) -> None:
        """POST snapshots current EquippedItem rows into the new outfit."""
        # Pre-equip two items so save_outfit captures them.
        equip_item(
            character_sheet=self.sheet_a,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        equip_item(
            character_sheet=self.sheet_a,
            item_instance=self.glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        response = self.client.post(
            "/api/items/outfits/",
            {
                "character_sheet": self.sheet_a.pk,
                "wardrobe": self.wardrobe.pk,
                "name": "CreatedLook",
                "description": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        outfit = Outfit.objects.get(character_sheet=self.sheet_a, name="CreatedLook")
        slot_tuples = {
            (s.item_instance_id, s.body_region, s.equipment_layer) for s in outfit.slots.all()
        }
        self.assertEqual(
            slot_tuples,
            {
                (self.shirt.pk, BodyRegion.TORSO, EquipmentLayer.BASE),
                (self.glove.pk, BodyRegion.LEFT_HAND, EquipmentLayer.BASE),
            },
        )

        # Cleanup so other tests don't see the equipped rows.
        EquippedItem.objects.filter(character=self.character_a).delete()

    def test_create_rejects_when_wardrobe_unreachable(self) -> None:
        """POST with a wardrobe in a different room → 400 (NotReachable).

        Regression test for I4: previously save_outfit's docstring claimed
        REST validated reach, but no permission class actually checked. The
        service now validates reach itself, and the serializer surfaces it
        as a 400 ValidationError on the wardrobe field.
        """
        other_room = ObjectDBFactory(
            db_key="OutfitViewOtherRoomForReach",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        # Move our wardrobe somewhere the actor can't see.
        self.wardrobe.game_object.location = other_room
        self.wardrobe.game_object.save()

        response = self.client.post(
            "/api/items/outfits/",
            {
                "character_sheet": self.sheet_a.pk,
                "wardrobe": self.wardrobe.pk,
                "name": "UnreachableWardrobeLook",
                "description": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("can't reach that", str(response.data))
        self.assertFalse(
            Outfit.objects.filter(
                character_sheet=self.sheet_a, name="UnreachableWardrobeLook"
            ).exists()
        )

    def test_create_rejects_non_wardrobe_template(self) -> None:
        """POST with a wardrobe arg pointing at a non-wardrobe item → 400."""
        non_wardrobe_obj = ObjectDBFactory(
            db_key="OutfitViewNonWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        non_wardrobe = ItemInstanceFactory(
            template=self.shirt_template,  # not a wardrobe template
            game_object=non_wardrobe_obj,
        )

        response = self.client.post(
            "/api/items/outfits/",
            {
                "character_sheet": self.sheet_a.pk,
                "wardrobe": non_wardrobe.pk,
                "name": "ShouldFailLook",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("isn't a container", str(response.data))
        self.assertFalse(
            Outfit.objects.filter(character_sheet=self.sheet_a, name="ShouldFailLook").exists()
        )

    def test_create_rejects_when_not_playing_character(self) -> None:
        """Account that doesn't play sheet A cannot save an outfit on it."""
        self.client.force_authenticate(user=self.account_b)

        response = self.client.post(
            "/api/items/outfits/",
            {
                "character_sheet": self.sheet_a.pk,
                "wardrobe": self.wardrobe.pk,
                "name": "NotMyLook",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            Outfit.objects.filter(character_sheet=self.sheet_a, name="NotMyLook").exists()
        )

    # ------------------------------------------------------------------
    # PATCH (rename / redescribe)
    # ------------------------------------------------------------------

    def test_partial_update_can_rename(self) -> None:
        """PATCH renames an existing outfit."""
        outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="OldLook",
        )
        response = self.client.patch(
            f"/api/items/outfits/{outfit.pk}/",
            {"name": "NewLook"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        outfit.refresh_from_db()
        self.assertEqual(outfit.name, "NewLook")

    def test_patch_cannot_change_character_sheet(self) -> None:
        """PATCH attempting to change character_sheet is silently dropped.

        Regression test for I5: previously the write serializer listed
        character_sheet on Meta.fields without read-only restrictions, so
        PATCH could transfer an outfit to a different character.
        """
        outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="WriteOnceSheetLook",
        )
        original_sheet_id = outfit.character_sheet_id

        response = self.client.patch(
            f"/api/items/outfits/{outfit.pk}/",
            {"character_sheet": self.sheet_b.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        outfit.refresh_from_db()
        self.assertEqual(outfit.character_sheet_id, original_sheet_id)

    def test_patch_cannot_change_wardrobe(self) -> None:
        """PATCH attempting to change wardrobe is silently dropped.

        Regression test for I5: previously wardrobe was a writable field on
        update, so PATCH could relocate the outfit's anchor to any item.
        """
        outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="WriteOnceWardrobeLook",
        )
        original_wardrobe_id = outfit.wardrobe_id

        # Build a different wardrobe-templated item to attempt to swap to.
        other_wardrobe_obj = ObjectDBFactory(
            db_key="OutfitViewOtherWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        other_wardrobe_obj.location = self.room
        other_wardrobe_obj.save()
        other_wardrobe = ItemInstanceFactory(
            template=self.wardrobe_template,
            game_object=other_wardrobe_obj,
        )

        response = self.client.patch(
            f"/api/items/outfits/{outfit.pk}/",
            {"wardrobe": other_wardrobe.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        outfit.refresh_from_db()
        self.assertEqual(outfit.wardrobe_id, original_wardrobe_id)

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def test_destroy_calls_delete_outfit_service(self) -> None:
        """DELETE removes the outfit row."""
        outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="DeleteMeLook",
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        outfit_pk = outfit.pk

        response = self.client.delete(f"/api/items/outfits/{outfit_pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Outfit.objects.filter(pk=outfit_pk).exists())

    def test_destroy_does_not_touch_items(self) -> None:
        """Items survive when the outfit is deleted."""
        outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="DeleteSpareItemsLook",
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        shirt_pk = self.shirt.pk

        response = self.client.delete(f"/api/items/outfits/{outfit.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(ItemInstance.objects.filter(pk=shirt_pk).exists())


class OutfitSlotViewSetTests(_OutfitViewSetSetupMixin, TestCase):
    """Tests for /api/items/outfit-slots/."""

    def setUp(self) -> None:
        super().setUp()
        self.outfit = OutfitFactory(
            character_sheet=self.sheet_a,
            wardrobe=self.wardrobe,
            name="SlotViewLook",
        )

    def test_create_adds_slot(self) -> None:
        """POST adds a new slot to the outfit."""
        response = self.client.post(
            "/api/items/outfit-slots/",
            {
                "outfit": self.outfit.pk,
                "item_instance": self.shirt.pk,
                "body_region": BodyRegion.TORSO,
                "equipment_layer": EquipmentLayer.BASE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.outfit.slots.count(), 1)
        slot = self.outfit.slots.first()
        self.assertEqual(slot.item_instance_id, self.shirt.pk)
        self.assertEqual(slot.body_region, BodyRegion.TORSO)
        self.assertEqual(slot.equipment_layer, EquipmentLayer.BASE)

    def test_create_replaces_existing_slot_at_same_region_layer(self) -> None:
        """A second POST at the same (region, layer) replaces the existing slot."""
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        # Build a second TORSO/BASE-compatible item, owned by the same account.
        other_shirt_obj = ObjectDBFactory(
            db_key="OutfitViewOtherShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        other_shirt_obj.location = self.character_a
        other_shirt_obj.save()
        other_shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=other_shirt_obj,
            owner=self.account_a,
        )

        response = self.client.post(
            "/api/items/outfit-slots/",
            {
                "outfit": self.outfit.pk,
                "item_instance": other_shirt.pk,
                "body_region": BodyRegion.TORSO,
                "equipment_layer": EquipmentLayer.BASE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        slots = self.outfit.slots.all()
        self.assertEqual(slots.count(), 1)
        self.assertEqual(slots.first().item_instance_id, other_shirt.pk)

    def test_create_rejects_template_incompatible(self) -> None:
        """POST with an item whose template doesn't declare (region, layer) → 400."""
        response = self.client.post(
            "/api/items/outfit-slots/",
            {
                "outfit": self.outfit.pk,
                "item_instance": self.slotless_item.pk,
                "body_region": BodyRegion.TORSO,
                "equipment_layer": EquipmentLayer.BASE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be worn there", str(response.data))
        self.assertEqual(self.outfit.slots.count(), 0)

    def test_create_rejects_item_owned_by_another_account(self) -> None:
        """POST with an item_instance whose owner is a different account → 400.

        Regression test for I1: previously the service+permission only checked
        the outfit's character_sheet, never the item's owner. A player could
        wedge any item id into their outfit slot rows.
        """
        # An item owned by account_b but referenced from account_a's outfit.
        foreign_obj = ObjectDBFactory(
            db_key="OutfitViewForeignItem",
            db_typeclass_path="typeclasses.objects.Object",
        )
        foreign_obj.location = self.character_b
        foreign_obj.save()
        foreign_item = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=foreign_obj,
            owner=self.account_b,
        )

        response = self.client.post(
            "/api/items/outfit-slots/",
            {
                "outfit": self.outfit.pk,
                "item_instance": foreign_item.pk,
                "body_region": BodyRegion.TORSO,
                "equipment_layer": EquipmentLayer.BASE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.outfit.slots.count(), 0)

    def test_destroy_removes_slot(self) -> None:
        """DELETE removes the slot row."""
        slot = OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        slot_pk = slot.pk

        response = self.client.delete(f"/api/items/outfit-slots/{slot_pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(OutfitSlot.objects.filter(pk=slot_pk).exists())

    def test_create_rejects_when_not_playing_character(self) -> None:
        """Account that doesn't play sheet A can't add a slot to its outfit."""
        self.client.force_authenticate(user=self.account_b)

        response = self.client.post(
            "/api/items/outfit-slots/",
            {
                "outfit": self.outfit.pk,
                "item_instance": self.shirt.pk,
                "body_region": BodyRegion.TORSO,
                "equipment_layer": EquipmentLayer.BASE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.outfit.slots.count(), 0)

    def test_list_excludes_other_users_outfit_slots(self) -> None:
        """A non-staff user cannot list slots that belong to another user's outfit."""
        other_outfit = OutfitFactory(
            character_sheet=self.sheet_b,
            wardrobe=self.wardrobe,
            name="OtherSlotOwnerLook",
        )
        # Build a slot on the other user's outfit; we expect it to be hidden.
        other_slot = OutfitSlotFactory(
            outfit=other_outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        response = self.client.get("/api/items/outfit-slots/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(other_slot.pk, result_ids)

    def test_staff_sees_all_outfit_slots(self) -> None:
        """Staff users bypass the per-account scope on the outfit-slot list."""
        # Build slots in two outfits (one per sheet).
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        other_outfit = OutfitFactory(
            character_sheet=self.sheet_b,
            wardrobe=self.wardrobe,
            name="StaffSlotOtherOwnerLook",
        )
        OutfitSlotFactory(
            outfit=other_outfit,
            item_instance=self.glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        staff = AccountFactory(username="outfit_slot_view_staff", is_staff=True)
        self.client.force_authenticate(user=staff)

        response = self.client.get("/api/items/outfit-slots/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Expect both this-test's slots represented (staff sees both outfits).
        # We can't assert exactly two because other tests in this DB run could
        # have created slots, but we can confirm both names appear.
        outfit_ids_in_response = {row["outfit"] for row in response.data["results"]}
        self.assertIn(self.outfit.pk, outfit_ids_in_response)
        self.assertIn(other_outfit.pk, outfit_ids_in_response)
