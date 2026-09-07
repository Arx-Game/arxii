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

    # --- base_power is magnitude, not intent (#3682, ADR-0281) ---

    def test_defense_effect_type_with_base_power_is_not_hostile(self):
        """A power-scaled DEFENSE technique with no hostile payload is benign.

        The authored ``Defense`` effect type carries base_power 10 — it is a
        power-*scaled* effect, which used to be read as a hostile one. Every
        Defense technique in the catalog therefore classified as hostile, so a
        shield cast at an ally routed through the attack path and a self-shield
        could not name its own caster as a target. Uses a non-null-power effect
        type deliberately: a null-power factory default would pass this test
        without exercising the branch that was wrong.
        """
        from world.magic.factories import EffectTypeFactory, TechniqueFactory
        from world.magic.services.hostility import is_technique_hostile

        effect_type = EffectTypeFactory(name="Defense", base_power=10)
        # damage_profile=False suppresses the factory's auto-seeded profile, so
        # base_power is the only thing that could make this read hostile.
        technique = TechniqueFactory(effect_type=effect_type, damage_profile=False)
        self.assertFalse(is_technique_hostile(technique))

    def test_self_shield_with_base_power_effect_type_targets_self(self):
        """A base_power Defense technique applying a SELF condition derives SELF.

        The relationship is what the cast gate actually enforces: ENEMY refuses
        to let the caster be a target at all, so this is the difference between
        a self-shield working and a self-shield being rejected.
        """
        from world.magic.factories import (
            EffectTypeFactory,
            TechniqueAppliedConditionFactory,
            TechniqueFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.targeting import derive_target_relationship

        technique = TechniqueFactory(
            effect_type=EffectTypeFactory(name="Defense", base_power=10),
            damage_profile=False,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.SELF,
        )
        self.assertEqual(derive_target_relationship(technique), ConditionTargetKind.SELF)

    def test_base_power_attack_with_damage_profile_stays_hostile(self):
        """Dropping the base_power shortcut must not disarm real offense.

        An Attack technique is hostile on its damage profile, which is what the
        authored offensive catalog actually carries — checked against the live
        catalog before the shortcut was removed: every Attack, Ranged Attack and
        Weapon Enhancement technique kept its hostile classification, and only
        Defense changed.
        """
        from world.magic.factories import EffectTypeFactory, TechniqueDamageProfileFactory
        from world.magic.services.hostility import is_technique_hostile

        profile = TechniqueDamageProfileFactory(
            base_damage=6,
            technique__effect_type=EffectTypeFactory(name="Attack", base_power=10),
        )
        self.assertTrue(is_technique_hostile(profile.technique))

    # --- Dispel targeting/hostility (#1585) ---

    def test_enemy_removed_condition_makes_technique_hostile(self):
        """Stripping a condition off an ENEMY (dispelling an enemy buff) is hostile."""
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            TechniqueFactory,
            TechniqueRemovedConditionFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.hostility import is_technique_hostile

        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueRemovedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.ENEMY,
        )
        self.assertTrue(is_technique_hostile(technique))

    def test_ally_removed_condition_is_not_hostile(self):
        """Cleansing a condition off an ALLY (dispelling an ally debuff) is not hostile."""
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            TechniqueFactory,
            TechniqueRemovedConditionFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.hostility import is_technique_hostile

        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueRemovedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.ALLY,
        )
        self.assertFalse(is_technique_hostile(technique))

    def test_self_removed_condition_is_not_hostile(self):
        """A self-cleanse dispel technique is not hostile."""
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            TechniqueFactory,
            TechniqueRemovedConditionFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.hostility import is_technique_hostile

        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueRemovedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.SELF,
        )
        self.assertFalse(is_technique_hostile(technique))
