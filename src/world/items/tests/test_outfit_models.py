"""Tests for the Outfit and OutfitSlot models and the ItemTemplate.is_wardrobe flag."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    OutfitSlotFactory,
    TemplateSlotFactory,
)
from world.items.models import Outfit, OutfitSlot


class ItemTemplateWardrobeFlagTests(TestCase):
    """Cover the new ``is_wardrobe`` flag on ItemTemplate."""

    def test_default_is_wardrobe_false(self) -> None:
        template = ItemTemplateFactory(name="Plain Shirt")
        self.assertFalse(template.is_wardrobe)

    def test_can_be_set_to_true(self) -> None:
        template = ItemTemplateFactory(
            name="Carved Wardrobe",
            is_wardrobe=True,
            is_container=True,
            container_capacity=20,
        )
        template.refresh_from_db()
        self.assertTrue(template.is_wardrobe)


class OutfitModelTests(TestCase):
    """Cover Outfit invariants: creation, uniqueness, cascade behavior."""

    def setUp(self) -> None:
        # Per-test setup: Evennia DbHolder isn't deepcopy-safe, so we cannot
        # use setUpTestData (see test_inventory_services.py).
        self.character = ObjectDBFactory(
            db_key="OutfitTestChar",
            db_typeclass_path="typeclasses.characters.Character",
        )
        self.sheet = CharacterSheetFactory(character=self.character)

        self.wardrobe_template = ItemTemplateFactory(
            name="Outfit Test Wardrobe",
            is_wardrobe=True,
            is_container=True,
            container_capacity=20,
        )
        self.wardrobe = ItemInstanceFactory(template=self.wardrobe_template)

    def test_can_create_outfit(self) -> None:
        outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="Court Attire",
        )
        outfit.refresh_from_db()
        self.assertEqual(outfit.name, "Court Attire")
        self.assertEqual(outfit.character_sheet, self.sheet)
        self.assertEqual(outfit.wardrobe, self.wardrobe)

    def test_unique_name_per_character_sheet(self) -> None:
        OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="Court Attire",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OutfitFactory(
                    character_sheet=self.sheet,
                    wardrobe=self.wardrobe,
                    name="Court Attire",
                )

    def test_different_characters_can_share_outfit_names(self) -> None:
        OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="Court Attire",
        )

        other_character = ObjectDBFactory(
            db_key="OtherChar",
            db_typeclass_path="typeclasses.characters.Character",
        )
        other_sheet = CharacterSheetFactory(character=other_character)
        other_wardrobe = ItemInstanceFactory(template=self.wardrobe_template)

        # Should not raise — different character.
        OutfitFactory(
            character_sheet=other_sheet,
            wardrobe=other_wardrobe,
            name="Court Attire",
        )

        self.assertEqual(Outfit.objects.filter(name="Court Attire").count(), 2)

    def test_deleting_wardrobe_cascades_outfit(self) -> None:
        outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="Court Attire",
        )
        outfit_pk = outfit.pk

        self.wardrobe.delete()

        self.assertFalse(Outfit.objects.filter(pk=outfit_pk).exists())


class OutfitSlotModelTests(TestCase):
    """Cover OutfitSlot invariants."""

    def setUp(self) -> None:
        self.character = ObjectDBFactory(
            db_key="OutfitSlotTestChar",
            db_typeclass_path="typeclasses.characters.Character",
        )
        self.sheet = CharacterSheetFactory(character=self.character)

        self.wardrobe_template = ItemTemplateFactory(
            name="OutfitSlot Test Wardrobe",
            is_wardrobe=True,
            is_container=True,
            container_capacity=20,
        )
        self.wardrobe = ItemInstanceFactory(template=self.wardrobe_template)

        self.outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="Court Attire",
        )

        self.shirt_template = ItemTemplateFactory(name="OutfitSlot Test Shirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.shirt = ItemInstanceFactory(template=self.shirt_template)

    def test_can_create_slot(self) -> None:
        slot = OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        slot.refresh_from_db()
        self.assertEqual(slot.outfit, self.outfit)
        self.assertEqual(slot.item_instance, self.shirt)
        self.assertEqual(slot.body_region, BodyRegion.TORSO)
        self.assertEqual(slot.equipment_layer, EquipmentLayer.BASE)

    def test_unique_per_outfit_region_layer(self) -> None:
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        other_shirt = ItemInstanceFactory(template=self.shirt_template)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OutfitSlotFactory(
                    outfit=self.outfit,
                    item_instance=other_shirt,
                    body_region=BodyRegion.TORSO,
                    equipment_layer=EquipmentLayer.BASE,
                )

    def test_deleting_outfit_cascades_slots(self) -> None:
        slot = OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        slot_pk = slot.pk

        self.outfit.delete()

        self.assertFalse(OutfitSlot.objects.filter(pk=slot_pk).exists())

    def test_deleting_item_cascades_slot(self) -> None:
        slot = OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        slot_pk = slot.pk

        self.shirt.delete()

        self.assertFalse(OutfitSlot.objects.filter(pk=slot_pk).exists())
