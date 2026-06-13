"""Tests for the equipped-gear combat contribution helpers (#508, Task 7)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.combat.services import effective_soak_from_armor, effective_weapon_profile
from world.conditions.factories import DamageTypeFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import EquippedItem


class EquipmentStatHelperTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="CombatWiringChar")

    def _equip(self, character, template, durability, body_region, quality=None):
        inst = ItemInstanceFactory(template=template, durability=durability, quality_tier=quality)
        EquippedItem.objects.create(
            character=character,
            item_instance=inst,
            body_region=body_region,
            equipment_layer=EquipmentLayer.BASE,
        )
        character.equipped_items.invalidate()
        return inst

    def test_soak_sums_equipped_armor(self):
        armor = ItemTemplateFactory(
            armor=True, name="hauberk", base_armor_soak=4, max_durability=10
        )
        self._equip(self.character, armor, 10, BodyRegion.TORSO)
        self.assertEqual(effective_soak_from_armor(self.character), 4)

    def test_broken_armor_contributes_no_soak(self):
        armor = ItemTemplateFactory(armor=True, name="broke", base_armor_soak=4, max_durability=10)
        self._equip(self.character, armor, 0, BodyRegion.TORSO)
        self.assertEqual(effective_soak_from_armor(self.character), 0)

    def test_weapon_profile_returns_highest_damage(self):
        dt = DamageTypeFactory(name="slash")
        weap = ItemTemplateFactory(
            weapon=True,
            name="saber",
            base_weapon_damage=6,
            weapon_damage_type=dt,
            max_durability=10,
        )
        self._equip(self.character, weap, 10, BodyRegion.RIGHT_HAND)
        prof = effective_weapon_profile(self.character)
        self.assertEqual(prof.damage, 6)
        self.assertEqual(prof.damage_type, dt)

    def test_no_weapon_returns_none(self):
        self.assertIsNone(effective_weapon_profile(self.character))
