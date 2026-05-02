"""Tests for TechniqueDamageProfile model and compute_damage_budget formula."""

from decimal import Decimal
import unittest

from django.db import IntegrityError, transaction
from evennia.utils.test_resources import EvenniaTestCase


class ComputeDamageBudgetTests(EvenniaTestCase):
    def test_baseline(self):
        from world.magic.factories import TechniqueDamageProfileFactory

        p = TechniqueDamageProfileFactory(
            base_damage=5,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=0,
            minimum_success_level=1,
        )
        self.assertEqual(p.compute_damage_budget(effective_intensity=0, success_level=1), 5)
        self.assertEqual(p.compute_damage_budget(effective_intensity=10, success_level=3), 5)

    def test_intensity_scaling(self):
        from world.magic.factories import TechniqueDamageProfileFactory

        p = TechniqueDamageProfileFactory(
            base_damage=2,
            damage_intensity_multiplier=Decimal("1.5"),
            damage_per_extra_sl=0,
            minimum_success_level=1,
        )
        # 2 + floor(1.5 * 4) = 2 + 6 = 8
        self.assertEqual(p.compute_damage_budget(effective_intensity=4, success_level=1), 8)

    def test_sl_kicker(self):
        from world.magic.factories import TechniqueDamageProfileFactory

        p = TechniqueDamageProfileFactory(
            base_damage=2,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=2,
            minimum_success_level=1,
        )
        # SL=1: 2 + 0 = 2
        self.assertEqual(p.compute_damage_budget(effective_intensity=0, success_level=1), 2)
        # SL=3: 2 + 2*2 = 6
        self.assertEqual(p.compute_damage_budget(effective_intensity=0, success_level=3), 6)


@unittest.skip("requires Task 5 — TechniqueFactory.post_generation damage_profile kwarg")
class UniqueConstraintTests(EvenniaTestCase):
    """Run AFTER Task 5 lands the post_generation skip kwarg.

    Until then, instantiate the technique directly via ORM to avoid
    the auto-seeded damage profile from TechniqueFactory.post_generation.
    """

    def test_unique_per_technique_per_typed_pair(self):
        from world.conditions.factories import DamageTypeFactory
        from world.magic.factories import (
            TechniqueDamageProfileFactory,
            TechniqueFactory,
        )

        # Use damage_profile=False to skip auto-seeding (Task 5 wires this).
        # If Task 5 isn't done yet, FactoryBoy ignores unknown kwargs and may
        # auto-seed an untyped row. Pass typed=Fire below — duplicate fire row
        # raises regardless.
        tech = TechniqueFactory(damage_profile=False)
        fire = DamageTypeFactory(name="Fire")
        TechniqueDamageProfileFactory(technique=tech, damage_type=fire)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TechniqueDamageProfileFactory(technique=tech, damage_type=fire)

    def test_null_damage_type_unique_per_technique(self):
        from world.magic.factories import (
            TechniqueDamageProfileFactory,
            TechniqueFactory,
        )

        tech = TechniqueFactory(damage_profile=False)
        TechniqueDamageProfileFactory(technique=tech, damage_type=None)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TechniqueDamageProfileFactory(technique=tech, damage_type=None)
