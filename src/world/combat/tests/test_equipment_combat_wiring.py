"""Tests for the equipped-gear combat contribution helpers (#508, Task 7)."""

from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.combat.factories import CombatParticipantFactory
from world.combat.services import (
    apply_damage_to_participant,
    effective_soak_from_armor,
    effective_weapon_profile,
)
from world.combat.tests.test_combat_technique_resolver import _build_resolver
from world.conditions.factories import (
    DamageSuccessLevelMultiplierFactory,
    DamageTypeFactory,
)
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import EquippedItem
from world.magic.factories import TechniqueDamageProfileFactory
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


class WeaponDamageWiringTests(TestCase):
    """Equipped-weapon damage augments a uses_equipped_weapon profile and the
    landed hit wears the weapon (#508, Task 9)."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Seed the SL multiplier lookup so get_damage_multiplier returns 1.0 at SL=2.
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def _equip_weapon(self, character, *, damage, damage_type, durability):
        template = ItemTemplateFactory(
            weapon=True,
            name="wired-saber",
            base_weapon_damage=damage,
            weapon_damage_type=damage_type,
            max_durability=10,
        )
        inst = ItemInstanceFactory(template=template, durability=durability)
        EquippedItem.objects.create(
            character=character,
            item_instance=inst,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        character.equipped_items.invalidate()
        return inst

    def _weapon_profile_resolver(self, *, uses_equipped_weapon):
        """Resolver whose single profile yields a deterministic 0 base budget."""
        resolver = _build_resolver(base_power=20)
        resolver.action.focused_action.damage_profiles.all().delete()
        TechniqueDamageProfileFactory(
            technique=resolver.action.focused_action,
            base_damage=0,
            damage_type=None,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=0,
            minimum_success_level=1,
            uses_equipped_weapon=uses_equipped_weapon,
        )
        return resolver

    def test_equipped_weapon_adds_damage_uses_its_type_and_wears(self) -> None:
        resolver = self._weapon_profile_resolver(uses_equipped_weapon=True)
        attacker = resolver.participant.character_sheet.character
        weapon_dt = DamageTypeFactory(name="wired-slash")
        weapon = self._equip_weapon(attacker, damage=6, damage_type=weapon_dt, durability=10)

        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check, eff_intensity=0)

        # Profile contributes 0; weapon adds +6; SL=2 → multiplier 1.0; soak 0 →
        # 6 damage dealt.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].damage_dealt, 6)

        # Weapon's damage_type was used (the profile's own is None): verify the
        # opponent's resistance to that type was consulted by checking wear and
        # damage value — and confirm the weapon lost 1 durability.
        weapon.refresh_from_db()
        self.assertEqual(weapon.durability, 9)

    def test_weapon_damage_type_passed_when_profile_type_none(self) -> None:
        """With the profile's damage_type None, the weapon's type is what
        apply_damage_to_opponent receives."""
        from unittest.mock import patch

        from world.combat.services import apply_damage_to_opponent as real_apply

        resolver = self._weapon_profile_resolver(uses_equipped_weapon=True)
        attacker = resolver.participant.character_sheet.character
        weapon_dt = DamageTypeFactory(name="passed-type")
        self._equip_weapon(attacker, damage=6, damage_type=weapon_dt, durability=10)

        captured: dict = {}

        def _spy(target, raw_damage, **kwargs):
            captured["damage_type"] = kwargs.get("damage_type")
            captured["raw_damage"] = raw_damage
            return real_apply(target, raw_damage, **kwargs)

        check = MagicMock(success_level=2)
        with patch("world.combat.services.apply_damage_to_opponent", side_effect=_spy):
            resolver._apply_damage(check, eff_intensity=0)

        # The weapon's damage_type flowed through (profile's own type is None),
        # and the raw damage budget included the weapon's +6.
        self.assertEqual(captured["damage_type"], weapon_dt)
        self.assertEqual(captured["raw_damage"], 6)

    def test_profile_not_using_weapon_ignores_it(self) -> None:
        resolver = self._weapon_profile_resolver(uses_equipped_weapon=False)
        attacker = resolver.participant.character_sheet.character
        weapon_dt = DamageTypeFactory(name="ignored-slash")
        weapon = self._equip_weapon(attacker, damage=6, damage_type=weapon_dt, durability=10)

        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check, eff_intensity=0)

        # base 0 budget + no weapon augmentation → scaled 0 → no result appended.
        self.assertEqual(results, [])

        # Weapon untouched — no landed weapon hit, so no durability wear.
        weapon.refresh_from_db()
        self.assertEqual(weapon.durability, 10)
