"""Tests for the derived technique hostility classifier."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase


class IsTechniqueHostileTests(EvenniaTestCase):
    """is_technique_hostile is a pure derived predicate — no model field."""

    def test_damage_profile_makes_technique_hostile(self):
        """A technique with a damage profile (base_damage > 0) is hostile."""
        from world.magic.factories import TechniqueDamageProfileFactory
        from world.magic.services.hostility import is_technique_hostile

        profile = TechniqueDamageProfileFactory(base_damage=5)
        self.assertTrue(is_technique_hostile(profile.technique))

    def test_enemy_condition_makes_technique_hostile(self):
        """A technique with an ENEMY-targeted condition application is hostile."""
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            TechniqueAppliedConditionFactory,
            TechniqueFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.hostility import is_technique_hostile

        # Use a binary effect type to avoid auto-seeded damage profile

        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.ENEMY,
        )
        self.assertTrue(is_technique_hostile(technique))

    def test_benign_technique_is_not_hostile(self):
        """A technique with no damage and no enemy conditions is benign."""
        from world.magic.factories import BinaryEffectTypeFactory, TechniqueFactory
        from world.magic.services.hostility import is_technique_hostile

        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        self.assertFalse(is_technique_hostile(technique))

    def test_self_targeted_condition_is_not_hostile(self):
        """A technique that applies a condition only to SELF is not hostile."""
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            TechniqueAppliedConditionFactory,
            TechniqueFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.hostility import is_technique_hostile

        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.SELF,
        )
        self.assertFalse(is_technique_hostile(technique))

    def test_ally_targeted_condition_is_not_hostile(self):
        """A technique that applies a condition only to ALLY is not hostile."""
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            TechniqueAppliedConditionFactory,
            TechniqueFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.hostility import is_technique_hostile

        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.ALLY,
        )
        self.assertFalse(is_technique_hostile(technique))

    def test_zero_base_damage_profile_is_not_hostile(self):
        """A damage profile with base_damage=0 does NOT make the technique hostile."""
        from world.magic.factories import BinaryEffectTypeFactory, TechniqueDamageProfileFactory
        from world.magic.services.hostility import is_technique_hostile

        profile = TechniqueDamageProfileFactory(
            base_damage=0,
            technique__effect_type=BinaryEffectTypeFactory(),
        )
        self.assertFalse(is_technique_hostile(profile.technique))

    def test_effect_type_with_base_power_makes_technique_hostile(self):
        """A technique whose effect_type has a non-null base_power is hostile."""
        from world.magic.factories import EffectTypeFactory, TechniqueFactory
        from world.magic.services.hostility import is_technique_hostile

        # EffectTypeFactory defaults base_power=10 and auto-seeds a damage profile.
        # Bypass damage_profile post_generation and supply an effect_type with
        # base_power set, to exercise the effect_type branch directly.
        effect_type = EffectTypeFactory(base_power=10)
        # damage_profile=False suppresses the auto-seeded profile so the
        # effect_type branch alone determines the result.
        technique = TechniqueFactory(effect_type=effect_type, damage_profile=False)
        self.assertTrue(is_technique_hostile(technique))
