"""Tests for #736 — equip/unequip wired into prestige_from_items recompute.

Verifies the wire-points added to ``equip_item`` and ``unequip_item``:
on equip success, the character_sheet's PRIMARY persona's
``prestige_from_items`` recomputes; same on unequip.

Also covers the place-XOR-equip gate that was Phase F's other half:
attempting to equip an item currently placed in a room raises
``ItemPlacedNotEquippable``.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.buildings.models import PolishCategory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.exceptions import ItemPlacedNotEquippable
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.polish_services import place_item_in_room
from world.items.services.equip import equip_item, unequip_item


def _make_decorative_template(polish_value: int, category: PolishCategory):
    template = ItemTemplateFactory(polish_value=polish_value, polish_category=category)
    TemplateSlotFactory(
        template=template,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )
    return template


class EquipRecomputesItemsPrestigeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="FashionTest")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.cat = PolishCategory.objects.create(name="Elegance")

    def test_equipping_polished_item_credits_primary_persona(self) -> None:
        template = _make_decorative_template(polish_value=40, category=self.cat)
        item = ItemInstanceFactory(template=template)
        persona = self.sheet.primary_persona

        equipped = equip_item(
            character_sheet=self.sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.assertIsNotNone(equipped.pk)

        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_items, 40)
        self.assertEqual(persona.total_prestige, 40)

    def test_unequipping_polished_item_zeros_credit(self) -> None:
        template = _make_decorative_template(polish_value=25, category=self.cat)
        item = ItemInstanceFactory(template=template)
        persona = self.sheet.primary_persona

        equipped = equip_item(
            character_sheet=self.sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_items, 25)

        unequip_item(equipped_item=equipped)
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_items, 0)

    def test_zero_polish_item_does_not_credit(self) -> None:
        template = ItemTemplateFactory(polish_value=0)
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item = ItemInstanceFactory(template=template)
        persona = self.sheet.primary_persona

        equip_item(
            character_sheet=self.sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_items, 0)


class PlaceEquipXORGateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="XORTest")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.cat = PolishCategory.objects.create(name="Elegance")

    def test_equipping_placed_item_raises_item_placed_not_equippable(self) -> None:
        template = _make_decorative_template(polish_value=10, category=self.cat)
        item = ItemInstanceFactory(template=template)
        room = RoomProfileFactory()
        place_item_in_room(item, room)

        with self.assertRaises(ItemPlacedNotEquippable):
            equip_item(
                character_sheet=self.sheet,
                item_instance=item,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )
