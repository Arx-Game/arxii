"""Tests for combat stat_override wiring (#2757, #2858, #2879)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.stat_mapping import DEFENSE_STAT, weapon_stat_override
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import EquippedItem, WeaponClass


class WeaponStatMappingTests(TestCase):
    """The weapon→stat mapping maps GearArchetype to a stat name."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory().character

    def _equip_weapon(
        self,
        archetype: str,
        name: str = "test_weapon",
        weapon_class: WeaponClass | None = None,
    ):
        template = ItemTemplateFactory(
            gear_archetype=archetype,
            base_weapon_damage=5,
            name=name,
            max_durability=30,
            weapon_class=weapon_class,
        )
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


class WeaponStatOverrideBlendTests(TestCase):
    """weapon_class overrides the coarse archetype mapping with a blend weight (#2879).

    ``weapon_stat_override`` returns ``weapon_class.strength_tenths`` (an int,
    0-10) when the equipped weapon's template is classified, falling back to
    the ``GearArchetype`` stat-name mapping (#2757) when it isn't.
    """

    def setUp(self):
        super().setUp()
        self.character = CharacterSheetFactory().character

    def _equip_weapon(
        self,
        archetype: str,
        name: str = "test_weapon",
        weapon_class: WeaponClass | None = None,
    ):
        template = ItemTemplateFactory(
            gear_archetype=archetype,
            base_weapon_damage=5,
            name=name,
            max_durability=30,
            weapon_class=weapon_class,
        )
        inst = ItemInstanceFactory(template=template, durability=30)
        EquippedItem.objects.create(
            character=self.character.sheet_data,
            item_instance=inst,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.character.equipped_items.invalidate()
        return inst

    def test_pure_strength_blend_returns_ten(self):
        wc = WeaponClass.objects.create(name="Brute", strength_tenths=10)
        self._equip_weapon(GearArchetype.MELEE_TWO_HAND, "maul", wc)
        self.assertEqual(weapon_stat_override(self.character), 10)

    def test_pure_agility_blend_returns_zero(self):
        wc = WeaponClass.objects.create(name="Precision weapon", strength_tenths=0)
        self._equip_weapon(GearArchetype.RANGED, "crossbow", wc)
        self.assertEqual(weapon_stat_override(self.character), 0)

    def test_even_blend_returns_five(self):
        wc = WeaponClass.objects.create(name="Balanced blade", strength_tenths=5)
        self._equip_weapon(GearArchetype.MELEE_ONE_HAND, "longsword", wc)
        self.assertEqual(weapon_stat_override(self.character), 5)

    def test_no_weapon_class_falls_back_to_archetype(self):
        self._equip_weapon(GearArchetype.MELEE_ONE_HAND, "dagger", None)
        self.assertEqual(weapon_stat_override(self.character), "agility")

    def test_no_weapon_returns_none(self):
        self.assertIsNone(weapon_stat_override(self.character))
