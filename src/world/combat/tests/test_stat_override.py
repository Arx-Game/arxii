"""Tests for combat stat_override wiring (#2757, #2858, #2879)."""

from __future__ import annotations

from django.test import TestCase, override_settings

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


@override_settings(SEED_SAMPLE_CONTENT=True)  # seed_combat_check_content gates on #2698
class WeaponClassCheckResolutionEndToEndTests(TestCase):
    """Cross the Task 2 (weapon_stat_override)/Task 3 (perform_check blend) seam (#2879).

    Every other test in this module (and in world/checks/tests/test_stat_override.py)
    exercises one side of the seam in isolation: weapon_stat_override's return value,
    or perform_check's blend arithmetic given an already-known int. Neither proves the
    two actually compose — that equipping a real, seeded WeaponClass produces a check
    rating that reflects its blend weight. This test equips the real seeded "Heavy
    blade" WeaponClass (strength_tenths=7, via seed_item_template_starter_catalog's
    Greatsword) and feeds weapon_stat_override's own return value straight into
    perform_check on the real seeded "Melee Combat" CheckType.
    """

    def setUp(self):
        super().setUp()
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        from world.seeds.combat_checks import seed_combat_check_content
        from world.traits.factories import CheckSystemSetupFactory
        from world.traits.models import ResultChart

        seed_combat_check_content()
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        from world.traits.models import PointConversionRange, TraitType

        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )

        self.character = CharacterSheetFactory().character

    def test_seeded_weapon_class_blend_reaches_perform_check(self):
        from world.checks.models import CheckType
        from world.checks.services import perform_check
        from world.seeds.game_content.items import seed_item_template_starter_catalog

        catalog = seed_item_template_starter_catalog()
        greatsword = catalog.templates[GearArchetype.MELEE_TWO_HAND]
        self.assertEqual(greatsword.weapon_class.name, "Heavy blade")
        self.assertEqual(greatsword.weapon_class.strength_tenths, 7)
        # The starter catalog doesn't set base_weapon_damage (that's authored
        # separately); _select_equipped_weapon requires positive effective damage
        # to consider an equipped item a weapon at all.
        greatsword.base_weapon_damage = greatsword.weapon_class.default_damage
        greatsword.save()

        inst = ItemInstanceFactory(template=greatsword, durability=30)
        EquippedItem.objects.create(
            character=self.character.sheet_data,
            item_instance=inst,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.character.equipped_items.invalidate()

        # weapon_stat_override reads the equipped Greatsword's WeaponClass and
        # returns its strength_tenths weight directly.
        stat_override = weapon_stat_override(self.character)
        self.assertEqual(stat_override, 7)

        self.character.traits.set_trait_value("strength", 10)
        self.character.traits.set_trait_value("agility", 3)

        melee_check = CheckType.objects.get(name="Melee Combat")
        result_blended = perform_check(self.character, melee_check, stat_override=stat_override)
        result_pure_strength = perform_check(self.character, melee_check, stat_override=10)

        # strength_tenths=7: (10*7 + 3*3) / 10 = 7.9 -> int truncation via
        # PointConversionRange gives a lower stat contribution than pure strength
        # (10*10 + 3*0)/10 = 10 would. If the WeaponClass's weight never reached
        # perform_check (composition broken), both calls would be identical.
        self.assertLess(result_blended.trait_points, result_pure_strength.trait_points)
        self.assertGreater(result_blended.trait_points, 0)
