"""Tests for the visible-worn-items service."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services.appearance import VisibleWornItem, visible_worn_items_for


class _Builder:
    """Test helper for visibility scenarios."""

    @classmethod
    def _make_character(cls, db_key: str):
        return CharacterFactory(db_key=db_key)

    @classmethod
    def _equip(cls, character, item, region, layer):
        return EquippedItem.objects.create(
            character=character,
            item_instance=item,
            body_region=region,
            equipment_layer=layer,
        )

    @classmethod
    def _make_item(cls, name: str, region: str, layer: str, *, covers: bool = False):
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template,
            body_region=region,
            equipment_layer=layer,
            covers_lower_layers=covers,
        )
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        return ItemInstanceFactory(template=template, game_object=item_obj)


class VisibleWornItemsServiceTests(_Builder, TestCase):
    def setUp(self) -> None:
        self.character = self._make_character("VisTestChar")

    def test_naked_character_returns_empty(self) -> None:
        self.assertEqual(visible_worn_items_for(self.character), [])

    def test_single_layer_returns_one_visible(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        result = visible_worn_items_for(self.character)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], VisibleWornItem)
        self.assertEqual(result[0].item_instance, shirt)
        self.assertEqual(result[0].body_region, BodyRegion.TORSO)
        self.assertEqual(result[0].equipment_layer, EquipmentLayer.BASE)

    def test_two_layers_no_covering_both_visible(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=False)
        self._equip(self.character, shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character)
        self.assertEqual(len(result), 2)

    def test_two_layers_with_covering_only_top_visible(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(self.character, shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character)
        names = [v.item_instance.display_name for v in result]
        self.assertIn("Coat", names)
        self.assertNotIn("Shirt", names)

    def test_three_layers_middle_covers_top_visible(self) -> None:
        # under (no cover) + base (covers) + over (no cover)
        # Expected: base and over visible; under hidden.
        camisole = self._make_item("Camisole", BodyRegion.TORSO, EquipmentLayer.UNDER, covers=False)
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE, covers=True)
        vest = self._make_item("Vest", BodyRegion.TORSO, EquipmentLayer.OVER, covers=False)
        self._equip(self.character, camisole, BodyRegion.TORSO, EquipmentLayer.UNDER)
        self._equip(self.character, shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, vest, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character)
        names = {v.item_instance.display_name for v in result}
        self.assertEqual(names, {"Shirt", "Vest"})

    def test_different_regions_unaffected_by_each_other(self) -> None:
        # Cloak covers shoulders/back at OVER; doesn't touch torso (no torso slot).
        cloak = self._make_item("Cloak", BodyRegion.SHOULDERS, EquipmentLayer.OVER, covers=True)
        torso_shirt = self._make_item("TorsoShirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, cloak, BodyRegion.SHOULDERS, EquipmentLayer.OVER)
        self._equip(self.character, torso_shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        result = visible_worn_items_for(self.character)
        names = {v.item_instance.display_name for v in result}
        self.assertEqual(names, {"Cloak", "TorsoShirt"})

    def test_self_observer_skips_hiding(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(self.character, shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character, observer=self.character)
        self.assertEqual(len(result), 2)

    def test_staff_observer_skips_hiding(self) -> None:
        staff_account = AccountFactory(username="staff_observer")
        staff_account.is_staff = True
        staff_account.save()
        staff_character = self._make_character("StaffChar")
        staff_character.db_account = staff_account
        staff_character.save()

        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(self.character, shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character, observer=staff_character)
        self.assertEqual(len(result), 2)

    def test_non_staff_observer_sees_only_visible(self) -> None:
        observer_account = AccountFactory(username="observer_account")
        observer_account.is_staff = False
        observer_account.save()
        observer = self._make_character("OtherChar")
        observer.db_account = observer_account
        observer.save()

        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(self.character, shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(self.character, coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character, observer=observer)
        names = [v.item_instance.display_name for v in result]
        self.assertEqual(names, ["Coat"])
