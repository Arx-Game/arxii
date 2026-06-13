"""Tests for the equipped-gear combat contribution helpers (#508, Task 7)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.combat.factories import CombatParticipantFactory
from world.combat.services import (
    apply_damage_to_participant,
    effective_soak_from_armor,
    effective_weapon_profile,
)
from world.conditions.factories import DamageTypeFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import EquippedItem
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals


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


class ArmorSoakDamageWiringTests(TestCase):
    """Equipped-armor soak reduces PC damage and wears the armor (#508, Task 8)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.participant = CombatParticipantFactory()

    def setUp(self) -> None:
        self.character = self.participant.character_sheet.character
        self.vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=self.participant.character_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        self.vitals.health = 100
        self.vitals.max_health = 100
        self.vitals.life_state = CharacterLifeState.ALIVE
        self.vitals.save()

    def _equip(self, template, durability, body_region):
        inst = ItemInstanceFactory(template=template, durability=durability)
        EquippedItem.objects.create(
            character=self.character,
            item_instance=inst,
            body_region=body_region,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.character.equipped_items.invalidate()
        return inst

    def test_armor_soak_reduces_damage_and_wears_armor(self):
        armor_template = ItemTemplateFactory(
            armor=True, name="soak-hauberk", base_armor_soak=4, max_durability=10
        )
        armor = self._equip(armor_template, 10, BodyRegion.TORSO)

        baseline = self.vitals.health
        apply_damage_to_participant(self.participant, 10, damage_type=None)

        self.vitals.refresh_from_db()
        # 10 raw damage - 4 soak = 6 health lost.
        self.assertEqual(self.vitals.health, baseline - 6)

        armor.refresh_from_db()
        # The piece absorbed damage, so it took 1 point of durability wear.
        self.assertEqual(armor.durability, 9)
