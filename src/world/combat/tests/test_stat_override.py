"""Tests for combat stat_override wiring (#2757)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.stat_mapping import DEFENSE_STAT, weapon_stat_override
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import EquippedItem


class WeaponStatMappingTests(TestCase):
    """The weapon→stat mapping maps GearArchetype to a stat name."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory().character

    def _equip_weapon(self, archetype: str, name: str = "test_weapon"):
        template = ItemTemplateFactory(
            gear_archetype=archetype,
            base_weapon_damage=5,
            name=name,
            max_durability=30,
        )
        inst = ItemTemplateFactory
        inst = ItemInstanceFactory(template=template, durability=30)
        EquippedItem.objects.create(
            character=self.character.sheet_data,
            item_instance=inst,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.character.equipped_items.invalidate()
        return inst

    def test_two_handed_maps_to_strength(self):
        self._equip_weapon(GearArchetype.MELEE_TWO_HAND, "warhammer")
        self.assertEqual(weapon_stat_override(self.character), "strength")

    def test_one_handed_maps_to_agility(self):
        self._equip_weapon(GearArchetype.MELEE_ONE_HAND, "rapier")
        self.assertEqual(weapon_stat_override(self.character), "agility")

    def test_ranged_maps_to_agility(self):
        self._equip_weapon(GearArchetype.RANGED, "bow")
        self.assertEqual(weapon_stat_override(self.character), "agility")

    def test_thrown_maps_to_strength(self):
        self._equip_weapon(GearArchetype.THROWN, "javelin")
        self.assertEqual(weapon_stat_override(self.character), "strength")

    def test_lance_maps_to_strength(self):
        self._equip_weapon(GearArchetype.LANCE, "lance")
        self.assertEqual(weapon_stat_override(self.character), "strength")

    def test_no_weapon_returns_none(self):
        # Fresh character with no equipped weapon
        self.assertIsNone(weapon_stat_override(self.character))

    def test_defense_stat_is_agility(self):
        self.assertEqual(DEFENSE_STAT, "agility")
