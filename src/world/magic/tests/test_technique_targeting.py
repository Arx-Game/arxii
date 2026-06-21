from django.test import TestCase

from actions.constants import ActionTargetType
from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.targeting import (
    cast_requires_consent,
    derive_target_relationship,
    technique_alters_behavior,
)


class TechniqueTargetTypeTests(TestCase):
    def test_defaults_to_single(self):
        tech = TechniqueFactory()
        self.assertEqual(tech.target_type, ActionTargetType.SINGLE)

    def test_target_type_authorable(self):
        tech = TechniqueFactory(target_type=ActionTargetType.AREA)
        self.assertEqual(tech.target_type, ActionTargetType.AREA)


class ConditionCategoryAltersBehaviorTests(TestCase):
    def test_alters_behavior_defaults_false(self):
        cat = ConditionCategoryFactory()
        self.assertFalse(cat.alters_behavior)


class DeriveTargetRelationshipTests(TestCase):
    """Tests for derive_target_relationship."""

    def test_hostile_technique_returns_enemy(self):
        """A technique with a damage profile (is_technique_hostile=True) → ENEMY."""
        # TechniqueFactory with damage_profile=True (the default) creates a DamageProfile
        # with base_damage>0 making it hostile.
        tech = TechniqueFactory(damage_profile=True)
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.ENEMY)

    def test_ally_condition_application_returns_ally(self):
        """A non-hostile technique with an ALLY condition application → ALLY."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=tech,
            target_kind=ConditionTargetKind.ALLY,
        )
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.ALLY)

    def test_self_only_technique_returns_self(self):
        """A non-hostile technique with only SELF conditions → SELF."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=tech,
            target_kind=ConditionTargetKind.SELF,
        )
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.SELF)

    def test_no_conditions_returns_self(self):
        """A non-hostile technique with no condition applications → SELF."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.SELF)

    def test_enemy_condition_alone_makes_hostile(self):
        """A technique with only ENEMY condition_applications (no damage) is hostile."""
        # is_technique_hostile also checks ENEMY condition_applications
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=tech,
            target_kind=ConditionTargetKind.ENEMY,
        )
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.ENEMY)


class TechniqueAltersBehaviorTests(TestCase):
    """Tests for technique_alters_behavior."""

    def test_behavior_category_condition_returns_true(self):
        """A technique applying a condition in a behavior-altering category → True."""
        behavior_cat = ConditionCategoryFactory(alters_behavior=True)
        condition = ConditionTemplateFactory(category=behavior_cat)
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, condition=condition)
        self.assertTrue(technique_alters_behavior(tech))

    def test_stat_category_condition_returns_false(self):
        """A technique applying a condition in a normal (stat) category → False."""
        stat_cat = ConditionCategoryFactory(alters_behavior=False)
        condition = ConditionTemplateFactory(category=stat_cat)
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, condition=condition)
        self.assertFalse(technique_alters_behavior(tech))

    def test_no_conditions_returns_false(self):
        """A technique with no applied conditions → False."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        self.assertFalse(technique_alters_behavior(tech))


class CastRequiresConsentTests(TestCase):
    """Tests for cast_requires_consent."""

    def test_behavior_altering_technique_requires_consent(self):
        """A technique with a behavior-altering condition → requires consent."""
        behavior_cat = ConditionCategoryFactory(alters_behavior=True)
        condition = ConditionTemplateFactory(category=behavior_cat)
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, condition=condition)
        self.assertTrue(cast_requires_consent(tech))

    def test_non_behavior_altering_technique_no_consent(self):
        """A technique without behavior-altering conditions → no consent required."""
        stat_cat = ConditionCategoryFactory(alters_behavior=False)
        condition = ConditionTemplateFactory(category=stat_cat)
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, condition=condition)
        self.assertFalse(cast_requires_consent(tech))
