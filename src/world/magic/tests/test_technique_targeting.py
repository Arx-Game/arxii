from django.core.exceptions import ValidationError
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
    InvalidCastTarget,
    cast_requires_consent,
    derive_target_relationship,
    technique_alters_behavior,
    validate_cast_target,
)
from world.scenes.factories import PersonaFactory


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


class ValidateCastTargetTests(TestCase):
    """Tests for validate_cast_target and InvalidCastTarget."""

    def test_invalid_cast_target_is_validation_error_subclass(self):
        """InvalidCastTarget must subclass django.core.exceptions.ValidationError."""
        self.assertTrue(issubclass(InvalidCastTarget, ValidationError))

    # --- SELF relationship (technique returns SELF from derive_target_relationship) ---

    def test_self_relationship_technique_at_other_raises(self):
        """A SELF-relationship technique cast at another persona → InvalidCastTarget."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.SELF)
        initiator = PersonaFactory()
        other = PersonaFactory()  # different character_sheet
        with self.assertRaises(InvalidCastTarget):
            validate_cast_target(
                technique=tech, initiator_persona=initiator, target_personas=[other]
            )

    def test_self_relationship_technique_at_initiator_ok(self):
        """A SELF-relationship technique with [initiator] as target → no raise."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.SELF)
        initiator = PersonaFactory()
        validate_cast_target(
            technique=tech, initiator_persona=initiator, target_personas=[initiator]
        )

    def test_self_relationship_technique_empty_targets_ok(self):
        """A SELF-relationship technique with empty target list → no raise."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.SELF)
        initiator = PersonaFactory()
        validate_cast_target(technique=tech, initiator_persona=initiator, target_personas=[])

    # --- ENEMY relationship (hostile technique) ---

    def test_hostile_technique_at_self_raises(self):
        """A hostile (ENEMY-relationship) technique cast at the initiator → InvalidCastTarget."""
        tech = TechniqueFactory()  # default base_power=10 → hostile → ENEMY
        initiator = PersonaFactory()
        with self.assertRaises(InvalidCastTarget):
            validate_cast_target(
                technique=tech, initiator_persona=initiator, target_personas=[initiator]
            )

    def test_hostile_technique_at_other_ok(self):
        """A hostile technique cast at a different persona → no raise."""
        tech = TechniqueFactory()
        initiator = PersonaFactory()
        other = PersonaFactory()
        validate_cast_target(technique=tech, initiator_persona=initiator, target_personas=[other])

    # --- ALLY relationship ---

    def test_ally_buff_at_other_ok(self):
        """A non-hostile ALLY-relationship technique cast at another persona → no raise."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.ALLY)
        initiator = PersonaFactory()
        other = PersonaFactory()
        validate_cast_target(technique=tech, initiator_persona=initiator, target_personas=[other])

    def test_ally_buff_at_self_ok(self):
        """An ALLY-relationship technique cast at the initiator is allowed (self is fine)."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.ALLY)
        initiator = PersonaFactory()
        validate_cast_target(
            technique=tech, initiator_persona=initiator, target_personas=[initiator]
        )

    # --- SINGLE cardinality (target_type) ---

    def test_single_target_type_two_targets_raises(self):
        """A SINGLE-cardinality technique with two targets → InvalidCastTarget."""
        tech = TechniqueFactory()  # default target_type=SINGLE
        self.assertEqual(tech.target_type, ActionTargetType.SINGLE)
        initiator = PersonaFactory()
        other1 = PersonaFactory()
        other2 = PersonaFactory()
        with self.assertRaises(InvalidCastTarget):
            validate_cast_target(
                technique=tech,
                initiator_persona=initiator,
                target_personas=[other1, other2],
            )

    def test_single_target_type_one_target_ok(self):
        """A SINGLE-cardinality technique with exactly one target → no raise (the target
        constraint)."""
        tech = TechniqueFactory()
        initiator = PersonaFactory()
        other = PersonaFactory()
        validate_cast_target(technique=tech, initiator_persona=initiator, target_personas=[other])

    # --- SELF cardinality (target_type == SELF) ---

    def test_self_target_type_at_other_raises(self):
        """target_type=SELF with a non-initiator target → InvalidCastTarget."""
        tech = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            target_type=ActionTargetType.SELF,
        )
        initiator = PersonaFactory()
        other = PersonaFactory()
        with self.assertRaises(InvalidCastTarget):
            validate_cast_target(
                technique=tech, initiator_persona=initiator, target_personas=[other]
            )

    def test_self_target_type_empty_ok(self):
        """target_type=SELF with empty target list → no raise."""
        tech = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            target_type=ActionTargetType.SELF,
        )
        initiator = PersonaFactory()
        validate_cast_target(technique=tech, initiator_persona=initiator, target_personas=[])

    def test_self_target_type_with_initiator_ok(self):
        """target_type=SELF with [initiator] → no raise."""
        tech = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            target_type=ActionTargetType.SELF,
        )
        initiator = PersonaFactory()
        validate_cast_target(
            technique=tech, initiator_persona=initiator, target_personas=[initiator]
        )
