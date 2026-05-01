"""Tests for outfit-related service functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from flows.object_states.character_state import CharacterState
from flows.object_states.outfit_state import OutfitState
from flows.service_functions.outfits import apply_outfit, undress
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.exceptions import NotReachable, PermissionDenied
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    OutfitSlotFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services import equip_item


class ApplyOutfitTests(TestCase):
    """Cover the validation + happy paths of ``apply_outfit``."""

    def setUp(self) -> None:
        # Per-test setUp — DbHolder isn't deepcopy-safe, so setUpTestData
        # breaks for Evennia typeclasses (matches test_inventory_services
        # pattern).
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="ApplyOutfitRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="ApplyOutfitChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Wardrobe in the same room as the actor.
        wardrobe_template = ItemTemplateFactory(
            name="ApplyOutfitWardrobe",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="ApplyOutfitWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = self.room
        wardrobe_obj.save()
        self.wardrobe = ItemInstanceFactory(
            template=wardrobe_template,
            game_object=wardrobe_obj,
        )

        # Templates: a TORSO/BASE shirt and a LEFT_HAND/BASE glove (distinct
        # body regions so they don't conflict with each other).
        self.shirt_template = ItemTemplateFactory(name="ApplyOutfitShirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.glove_template = ItemTemplateFactory(name="ApplyOutfitGlove")
        TemplateSlotFactory(
            template=self.glove_template,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        # Two distinct items in the actor's possession.
        shirt_obj = ObjectDBFactory(
            db_key="ApplyOutfitShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = self.character
        shirt_obj.save()
        self.shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=shirt_obj,
        )
        glove_obj = ObjectDBFactory(
            db_key="ApplyOutfitGloveObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        glove_obj.location = self.character
        glove_obj.save()
        self.glove = ItemInstanceFactory(
            template=self.glove_template,
            game_object=glove_obj,
        )

        # Build outfit with a slot referencing each item.
        self.outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="ApplyOutfitLook",
        )
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.outfit_state = OutfitState(self.outfit, context=ctx)

    def test_apply_equips_all_slots(self) -> None:
        """All outfit slots become EquippedItem rows."""
        apply_outfit(self.character_state, self.outfit_state)

        equipped = EquippedItem.objects.filter(character=self.character)
        self.assertEqual(equipped.count(), 2)
        self.assertTrue(equipped.filter(item_instance=self.shirt).exists())
        self.assertTrue(equipped.filter(item_instance=self.glove).exists())

    def test_apply_swaps_conflicting_slot(self) -> None:
        """A pre-existing item at TORSO/BASE is auto-swapped for the outfit's shirt."""
        # Pre-equip a different shirt at TORSO/BASE.
        other_shirt_obj = ObjectDBFactory(
            db_key="ApplyOutfitOtherShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        other_shirt_obj.location = self.character
        other_shirt_obj.save()
        other_shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=other_shirt_obj,
        )
        equip_item(
            character_sheet=self.sheet,
            item_instance=other_shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        apply_outfit(self.character_state, self.outfit_state)

        # Only the outfit's shirt is at TORSO/BASE — the old one was swapped out.
        torso_rows = EquippedItem.objects.filter(
            character=self.character,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.assertEqual(torso_rows.count(), 1)
        self.assertEqual(torso_rows.first().item_instance, self.shirt)

    def test_apply_leaves_unrelated_slots_alone(self) -> None:
        """A pre-existing item at NECK/ACCESSORY survives the apply (no clean-strip)."""
        necklace_template = ItemTemplateFactory(name="ApplyOutfitNecklace")
        TemplateSlotFactory(
            template=necklace_template,
            body_region=BodyRegion.NECK,
            equipment_layer=EquipmentLayer.ACCESSORY,
        )
        necklace_obj = ObjectDBFactory(
            db_key="ApplyOutfitNecklaceObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        necklace_obj.location = self.character
        necklace_obj.save()
        necklace = ItemInstanceFactory(
            template=necklace_template,
            game_object=necklace_obj,
        )
        equip_item(
            character_sheet=self.sheet,
            item_instance=necklace,
            body_region=BodyRegion.NECK,
            equipment_layer=EquipmentLayer.ACCESSORY,
        )

        apply_outfit(self.character_state, self.outfit_state)

        self.assertTrue(
            EquippedItem.objects.filter(
                character=self.character,
                item_instance=necklace,
            ).exists()
        )

    def test_apply_rejects_when_wardrobe_not_in_reach(self) -> None:
        """Wardrobe in another room → NotReachable, no slots equipped."""
        other_room = ObjectDBFactory(
            db_key="ApplyOutfitOtherRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.wardrobe.game_object.location = other_room
        self.wardrobe.game_object.save()

        with self.assertRaises(NotReachable):
            apply_outfit(self.character_state, self.outfit_state)
        self.assertFalse(EquippedItem.objects.filter(character=self.character).exists())

    def test_apply_rejects_when_item_not_in_reach(self) -> None:
        """An outfit slot's item lives in another character's inventory → NotReachable."""
        bystander = CharacterFactory(
            db_key="ApplyOutfitBystander",
            location=self.room,
        )
        self.shirt.game_object.location = bystander
        self.shirt.game_object.save()

        with self.assertRaises(NotReachable):
            apply_outfit(self.character_state, self.outfit_state)
        # Whole transaction rolls back — no rows created.
        self.assertFalse(EquippedItem.objects.filter(character=self.character).exists())

    def test_apply_rejects_outfit_belonging_to_different_character(self) -> None:
        """An outfit owned by another sheet → PermissionDenied."""
        other_character = CharacterFactory(
            db_key="ApplyOutfitOtherChar",
            location=self.room,
        )
        other_sheet = CharacterSheetFactory(character=other_character)
        other_outfit = OutfitFactory(
            character_sheet=other_sheet,
            wardrobe=self.wardrobe,
            name="ApplyOutfitOtherLook",
        )
        OutfitSlotFactory(
            outfit=other_outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        other_outfit_state = OutfitState(other_outfit, context=MagicMock())

        with self.assertRaises(PermissionDenied):
            apply_outfit(self.character_state, other_outfit_state)


class UndressTests(TestCase):
    """Cover ``undress`` for naked, single-item, and multi-item characters."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="UndressTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="UndressTestChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Three distinct items at three distinct body regions so they coexist.
        self.items: list = []
        for idx, (region, layer, name) in enumerate(
            [
                (BodyRegion.TORSO, EquipmentLayer.BASE, "UndressShirt"),
                (BodyRegion.LEFT_HAND, EquipmentLayer.BASE, "UndressGlove"),
                (BodyRegion.NECK, EquipmentLayer.ACCESSORY, "UndressNecklace"),
            ]
        ):
            template = ItemTemplateFactory(name=f"{name}Template{idx}")
            TemplateSlotFactory(
                template=template,
                body_region=region,
                equipment_layer=layer,
            )
            item_obj = ObjectDBFactory(
                db_key=f"{name}Obj",
                db_typeclass_path="typeclasses.objects.Object",
            )
            item_obj.location = self.character
            item_obj.save()
            item = ItemInstanceFactory(template=template, game_object=item_obj)
            self.items.append(item)

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)

    def _equip_all(self) -> None:
        for item in self.items:
            slot = item.template.cached_slots[0]
            equip_item(
                character_sheet=self.sheet,
                item_instance=item,
                body_region=slot.body_region,
                equipment_layer=slot.equipment_layer,
            )

    def test_undress_removes_all_equipped_items(self) -> None:
        """Three equipped items → zero EquippedItem rows after undress."""
        self._equip_all()
        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            3,
        )

        undress(self.character_state)

        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            0,
        )

    def test_undress_idempotent_when_naked(self) -> None:
        """Naked character → undress is a no-op, no error raised."""
        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            0,
        )

        # Should not raise.
        undress(self.character_state)

        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            0,
        )

    def test_undress_keeps_items_in_inventory(self) -> None:
        """After undress, every item's underlying ObjectDB still on character."""
        self._equip_all()

        undress(self.character_state)

        for item in self.items:
            item.game_object.refresh_from_db()
            self.assertEqual(item.game_object.location, self.character)
