"""Tests for equip_item and unequip_item service functions."""

from django.test import TestCase

from world.items.constants import BodyRegion, EquipmentLayer
from world.items.exceptions import SlotConflict, SlotIncompatible
from world.items.models import EquippedItem
from world.items.services.equip import equip_item


class EquipItemTests(TestCase):
    """Tests for equip_item."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import (
            ItemInstanceFactory,
            ItemTemplateFactory,
            TemplateSlotFactory,
        )

        cls.character = CharacterFactory(db_key="EquipTestChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # Template with a single TORSO/BASE slot.
        cls.template = ItemTemplateFactory(name="Test Shirt")
        cls.slot = TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item = ItemInstanceFactory(template=cls.template)

    def tearDown(self) -> None:
        # Clean up any EquippedItem rows between tests so setUpTestData state is reusable.
        EquippedItem.objects.filter(character=self.character).delete()
        self.character.equipped_items.invalidate()

    def test_happy_path_creates_equipped_item(self) -> None:
        equipped = equip_item(
            character_sheet=self.sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.assertIsNotNone(equipped.pk)
        self.assertEqual(equipped.character, self.character)
        self.assertEqual(equipped.item_instance, self.item)
        self.assertEqual(equipped.body_region, BodyRegion.TORSO)
        self.assertEqual(equipped.equipment_layer, EquipmentLayer.BASE)
        self.assertTrue(EquippedItem.objects.filter(pk=equipped.pk).exists())

    def test_handler_cache_invalidated_after_equip(self) -> None:
        # Warm the cache with an empty load.
        handler = self.character.equipped_items
        _ = list(handler)
        self.assertIsNotNone(handler._cached)

        equip_item(
            character_sheet=self.sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # Cache should have been cleared by the service.
        self.assertIsNone(handler._cached)
        # Re-iterating loads the new row.
        items = list(handler)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].item_instance_id, self.item.pk)

    def test_slot_conflict_raises_when_slot_occupied(self) -> None:
        # Occupy the slot first.
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        with self.assertRaises(SlotConflict):
            equip_item(
                character_sheet=self.sheet,
                item_instance=self.item,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )

    def test_slot_incompatible_raises_for_undeclared_slot(self) -> None:
        # TORSO/OVER is not declared on cls.template.
        with self.assertRaises(SlotIncompatible):
            equip_item(
                character_sheet=self.sheet,
                item_instance=self.item,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.OVER,
            )

    def test_slot_incompatible_raises_for_wrong_region(self) -> None:
        with self.assertRaises(SlotIncompatible):
            equip_item(
                character_sheet=self.sheet,
                item_instance=self.item,
                body_region=BodyRegion.HEAD,
                equipment_layer=EquipmentLayer.BASE,
            )
