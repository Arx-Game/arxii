from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.factories import DamageTypeFactory
from world.items.constants import GearArchetype
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, QualityTierFactory
from world.items.models import ItemTemplate


class ItemTemplateCombatStatConstraintTests(TestCase):
    def test_weapon_damage_requires_weapon_archetype(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemTemplate.objects.create(
                name="bad-vase-weapon",
                gear_archetype=GearArchetype.OTHER,
                base_weapon_damage=5,
            )

    def test_armor_soak_requires_armor_archetype(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemTemplate.objects.create(
                name="bad-vase-armor",
                gear_archetype=GearArchetype.OTHER,
                base_armor_soak=3,
            )

    def test_weapon_template_with_damage_is_valid(self):
        dt = DamageTypeFactory(name="slashing")
        tmpl = ItemTemplate.objects.create(
            name="longsword",
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
            base_weapon_damage=7,
            weapon_damage_type=dt,
            max_durability=30,
        )
        self.assertEqual(tmpl.base_weapon_damage, 7)


class ItemInstanceEffectiveStatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt = DamageTypeFactory(name="piercing")
        cls.tier_x2 = QualityTierFactory(name="Fine", stat_multiplier=Decimal("2.0"))

    def test_effective_weapon_damage_scales_by_quality(self):
        tmpl = ItemTemplateFactory(
            name="spear",
            gear_archetype=GearArchetype.MELEE_TWO_HAND,
            base_weapon_damage=5,
            weapon_damage_type=self.dt,
            max_durability=10,
        )
        inst = ItemInstanceFactory(template=tmpl, quality_tier=self.tier_x2, durability=10)
        self.assertEqual(inst.effective_weapon_damage, 10)
        self.assertEqual(inst.effective_weapon_damage_type, self.dt)

    def test_effective_armor_soak_scales_by_quality(self):
        tmpl = ItemTemplateFactory(
            name="mail",
            gear_archetype=GearArchetype.HEAVY_ARMOR,
            base_armor_soak=4,
            max_durability=10,
        )
        inst = ItemInstanceFactory(template=tmpl, quality_tier=self.tier_x2, durability=10)
        self.assertEqual(inst.effective_armor_soak, 8)

    def test_broken_item_contributes_zero(self):
        tmpl = ItemTemplateFactory(
            name="cracked-mail",
            gear_archetype=GearArchetype.LIGHT_ARMOR,
            base_armor_soak=4,
            max_durability=10,
        )
        inst = ItemInstanceFactory(template=tmpl, quality_tier=self.tier_x2, durability=0)
        self.assertTrue(inst.is_broken)
        self.assertEqual(inst.effective_armor_soak, 0)

    def test_untracked_durability_is_never_broken(self):
        tmpl = ItemTemplateFactory(
            name="plain-knife",
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
            base_weapon_damage=3,
        )
        inst = ItemInstanceFactory(template=tmpl, durability=None)
        self.assertFalse(inst.is_broken)
        self.assertEqual(inst.effective_weapon_damage, 3)


class CombatFactoryTraitTests(TestCase):
    def test_weapon_trait_builds_valid_template(self):
        from world.items.factories import ItemTemplateFactory

        tmpl = ItemTemplateFactory(weapon=True, name="trait-sword")
        self.assertGreater(tmpl.base_weapon_damage, 0)

    def test_armor_trait_builds_valid_template(self):
        from world.items.factories import ItemTemplateFactory

        tmpl = ItemTemplateFactory(armor=True, name="trait-jacket")
        self.assertGreater(tmpl.base_armor_soak, 0)
