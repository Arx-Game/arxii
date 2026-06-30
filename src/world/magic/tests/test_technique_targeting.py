from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import ActionTargetType
from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
    TechniqueRemovedConditionFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.targeting import (
    InvalidCastTarget,
    cast_requires_consent,
    derive_target_relationship,
    resolve_targets,
    technique_alters_behavior,
    validate_cast_target,
)
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory


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

    def test_ally_removed_condition_returns_ally(self):
        """A non-hostile dispel technique cleansing an ALLY debuff → ALLY (#1585)."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueRemovedConditionFactory(
            technique=tech,
            target_kind=ConditionTargetKind.ALLY,
        )
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.ALLY)

    def test_enemy_removed_condition_makes_hostile(self):
        """A dispel technique stripping an ENEMY buff is hostile → ENEMY (#1585)."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueRemovedConditionFactory(
            technique=tech,
            target_kind=ConditionTargetKind.ENEMY,
        )
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.ENEMY)

    def test_self_removed_condition_returns_self(self):
        """A self-cleanse dispel technique → SELF (#1585)."""
        tech = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueRemovedConditionFactory(
            technique=tech,
            target_kind=ConditionTargetKind.SELF,
        )
        self.assertEqual(derive_target_relationship(tech), ConditionTargetKind.SELF)


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


class ResolveTargetsTests(TestCase):
    """Tests for resolve_targets."""

    def _make_ally_technique(self, **kwargs):
        """Non-hostile ALLY-relationship technique."""
        tech = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(), damage_profile=False, **kwargs
        )
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.ALLY)
        return tech

    def _make_self_technique(self, **kwargs):
        """Non-hostile SELF-relationship technique."""
        tech = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(), damage_profile=False, **kwargs
        )
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.SELF)
        return tech

    def _add_persona_to_scene(self, scene, persona):
        """Create an Interaction linking persona to scene so _collect_personas sees them."""
        InteractionFactory(scene=scene, persona=persona)

    # --- SELF target_type ---

    def test_self_type_returns_initiator(self):
        """target_type=SELF → [initiator_persona] regardless of supplied_personas."""
        tech = self._make_self_technique(target_type=ActionTargetType.SELF)
        initiator = PersonaFactory()
        scene = SceneFactory()
        other = PersonaFactory()
        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[other],
        )
        self.assertEqual(result, [initiator])

    # --- SINGLE target_type ---

    def test_single_type_returns_first_supplied(self):
        """target_type=SINGLE → supplied_personas[:1]."""
        tech = self._make_ally_technique(target_type=ActionTargetType.SINGLE)
        initiator = PersonaFactory()
        scene = SceneFactory()
        target1 = PersonaFactory()
        target2 = PersonaFactory()
        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[target1, target2],
        )
        self.assertEqual(result, [target1])

    def test_single_type_empty_supplied_returns_empty(self):
        """target_type=SINGLE with no supplied → empty list."""
        tech = self._make_ally_technique(target_type=ActionTargetType.SINGLE)
        initiator = PersonaFactory()
        scene = SceneFactory()
        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[],
        )
        self.assertEqual(result, [])

    # --- AREA target_type ---

    def test_area_ally_technique_returns_all_others_in_scene(self):
        """AREA + ALLY relationship → all personas in scene except the initiator."""
        tech = self._make_ally_technique(target_type=ActionTargetType.AREA)
        initiator = PersonaFactory()
        ally1 = PersonaFactory()
        ally2 = PersonaFactory()
        scene = SceneFactory()
        self._add_persona_to_scene(scene, initiator)
        self._add_persona_to_scene(scene, ally1)
        self._add_persona_to_scene(scene, ally2)

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[],
        )
        result_ids = {p.pk for p in result}
        self.assertNotIn(initiator.pk, result_ids)
        self.assertIn(ally1.pk, result_ids)
        self.assertIn(ally2.pk, result_ids)

    def test_area_enemy_technique_excludes_initiator(self):
        """AREA + ENEMY relationship → all scene personas excluding the initiator."""
        # Explicitly mark as ENEMY by adding an ENEMY condition application.
        tech = TechniqueFactory(
            target_type=ActionTargetType.AREA,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.ENEMY)
        initiator = PersonaFactory()
        enemy1 = PersonaFactory()
        scene = SceneFactory()
        self._add_persona_to_scene(scene, initiator)
        self._add_persona_to_scene(scene, enemy1)

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[],
        )
        result_ids = {p.pk for p in result}
        self.assertNotIn(initiator.pk, result_ids)
        self.assertIn(enemy1.pk, result_ids)

    def test_area_self_relationship_returns_only_initiator(self):
        """AREA + SELF relationship → [initiator] only."""
        tech = self._make_self_technique(target_type=ActionTargetType.AREA)
        initiator = PersonaFactory()
        other = PersonaFactory()
        scene = SceneFactory()
        self._add_persona_to_scene(scene, initiator)
        self._add_persona_to_scene(scene, other)

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[],
        )
        result_sheet_ids = {p.character_sheet_id for p in result}
        self.assertEqual(len(result), 1)
        self.assertIn(initiator.character_sheet_id, result_sheet_ids)

    def test_area_self_relationship_initiator_no_interaction(self):
        """AREA + SELF returns [initiator] even if initiator has no Interaction in scene."""
        tech = self._make_self_technique(target_type=ActionTargetType.AREA)
        initiator = PersonaFactory()
        other = PersonaFactory()
        scene = SceneFactory()
        # Only add other to scene, NOT initiator.
        self._add_persona_to_scene(scene, other)

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[],
        )
        # Should return initiator even though they have no Interaction in scene.
        result_sheet_ids = {p.character_sheet_id for p in result}
        self.assertEqual(len(result), 1)
        self.assertIn(initiator.character_sheet_id, result_sheet_ids)

    def test_area_only_counts_personas_present_in_scene(self):
        """AREA does not include personas that never posted in the scene."""
        tech = self._make_ally_technique(target_type=ActionTargetType.AREA)
        initiator = PersonaFactory()
        in_scene = PersonaFactory()
        not_in_scene = PersonaFactory()
        scene = SceneFactory()
        self._add_persona_to_scene(scene, initiator)
        self._add_persona_to_scene(scene, in_scene)
        # not_in_scene is never added

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[],
        )
        result_ids = {p.pk for p in result}
        self.assertIn(in_scene.pk, result_ids)
        self.assertNotIn(not_in_scene.pk, result_ids)

    # --- FILTERED_GROUP target_type ---

    def test_filtered_group_intersects_supplied_with_area_eligible(self):
        """FILTERED_GROUP → only supplied_personas that are in the scene's eligible set."""
        tech = self._make_ally_technique(target_type=ActionTargetType.FILTERED_GROUP)
        initiator = PersonaFactory()
        in_scene = PersonaFactory()
        not_in_scene = PersonaFactory()
        scene = SceneFactory()
        self._add_persona_to_scene(scene, initiator)
        self._add_persona_to_scene(scene, in_scene)

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[in_scene, not_in_scene],
        )
        result_ids = {p.pk for p in result}
        self.assertIn(in_scene.pk, result_ids)
        self.assertNotIn(not_in_scene.pk, result_ids)

    def test_filtered_group_respects_relationship_exclusion(self):
        """FILTERED_GROUP with ENEMY relationship excludes the initiator even if supplied."""
        tech = TechniqueFactory(target_type=ActionTargetType.FILTERED_GROUP)
        initiator = PersonaFactory()
        enemy = PersonaFactory()
        scene = SceneFactory()
        self._add_persona_to_scene(scene, initiator)
        self._add_persona_to_scene(scene, enemy)

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[initiator, enemy],
        )
        result_ids = {p.pk for p in result}
        self.assertNotIn(initiator.pk, result_ids)
        self.assertIn(enemy.pk, result_ids)
