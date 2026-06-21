"""Tests for targeting integration in standalone cast services (#1321).

Covers:
(a) Self-buff technique → condition applied to caster on RESOLVED cast.
(b) Benign non-consent capability buff at another PC → RESOLVED immediately, condition applied.
(c) Benign behavior-altering cast at another PC → PENDING (consent required).
(d) Self-only technique cast at another PC → InvalidCastTarget raised.
(e) FILTERED_GROUP benign capability buff with picked subset → both targets get condition,
    third ally NOT in list does not (#1321).
(f) FILTERED_GROUP hostile cast with supplied_personas → InvalidCastTarget (deferred).
(g) FILTERED_GROUP behavior-altering cast with supplied_personas → InvalidCastTarget (deferred).
"""

from __future__ import annotations

from django.test import tag

from actions.constants import ActionTargetType
from actions.factories import ActionTemplateFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
from world.conditions.services import get_active_conditions
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.targeting import InvalidCastTarget
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.cast_services import request_technique_cast
from world.scenes.factories import InteractionFactory, PersonaFactory
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    attach_behavior_altering_condition,
    grant_technique,
)
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals


@tag("postgres")
class TestSelfBuffAppliesConditionToCaster(CastScenarioMixin):
    """A self-targeting benign technique with a SELF condition applies that condition on cast."""

    def test_self_buff_resolves_and_applies_condition(self) -> None:
        """SELF technique cast at self → RESOLVED + condition on caster."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        # SELF-kind condition — no ALLY conditions means derive_target_relationship → SELF.
        condition_tmpl = ConditionTemplateFactory()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition_tmpl,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=0,
        )
        grant_technique(self.caster, technique)

        caster_char = self.caster.character_sheet.character
        caster_char.location = self.scene.location
        caster_char.save()

        # Force a successful cast roll so the SL gate (minimum_success_level=0) is met
        # deterministically — a real d100 roll fails ~40% of the time and would skip
        # the condition (the cast itself still resolves regardless of SL).
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success):
            cast = request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
            )

        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)
        active = get_active_conditions(caster_char, condition=condition_tmpl)
        self.assertTrue(
            active.exists(),
            "Self-buff condition should be applied to the caster after a RESOLVED cast.",
        )


@tag("postgres")
class TestBenignNonConsentBuffAtOtherPC(CastScenarioMixin):
    """Benign non-consent capability buff at another PC resolves immediately + applies condition."""

    def test_benign_no_consent_at_other_pc_resolved_with_condition(self) -> None:
        """Benign ALLY technique (no behavior-altering) → RESOLVED, condition on target."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        # ALLY-kind condition that does NOT alter behavior → no consent needed.
        condition_tmpl = ConditionTemplateFactory()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition_tmpl,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=0,
        )
        grant_technique(self.caster, technique)

        caster_char = self.caster.character_sheet.character
        caster_char.location = self.scene.location
        caster_char.save()

        target_char = self.target.character_sheet.character
        target_char.location = self.scene.location
        target_char.save()

        # Force a successful cast roll so the SL gate (minimum_success_level=0) is met
        # deterministically — a real d100 roll fails ~40% of the time and would skip
        # the condition (the cast itself still resolves immediately regardless of SL).
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success):
            cast = request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                target_persona=self.target,
                technique=technique,
            )

        self.assertEqual(
            cast.request.status,
            ActionRequestStatus.RESOLVED,
            "Benign non-consent-required buff at another PC must resolve immediately.",
        )
        active = get_active_conditions(target_char, condition=condition_tmpl)
        self.assertTrue(
            active.exists(),
            "ALLY condition should be applied to the target after immediate resolution.",
        )


class TestBenignBehaviorAlteringCastIsPending(CastScenarioMixin):
    """A benign behavior-altering cast at another PC → PENDING (consent required)."""

    def test_behavior_altering_cast_at_other_pc_is_pending(self) -> None:
        """Technique with alters_behavior=True condition → PENDING, no result."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        # Attach a behavior-altering ALLY condition — makes cast_requires_consent return True.
        behavior_cat = ConditionCategoryFactory(alters_behavior=True)
        behavior_cond = ConditionTemplateFactory(category=behavior_cat)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=behavior_cond,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

        self.assertEqual(
            cast.request.status,
            ActionRequestStatus.PENDING,
            "Behavior-altering cast at another PC must be PENDING (consent required).",
        )
        self.assertIsNone(cast.result)


class TestSelfOnlyTechniqueCastAtOtherRaises(CastScenarioMixin):
    """A technique whose derived relationship is SELF cannot target another PC."""

    def test_self_relationship_at_other_pc_raises_invalid_cast_target(self) -> None:
        """SELF-relationship technique (no ALLY/hostile conditions) cast at another → raises."""
        # No damage profile (not hostile), no ALLY conditions →
        # derive_target_relationship returns SELF.
        # Casting at another PC must raise InvalidCastTarget via validate_cast_target.
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        # Add a SELF condition to make the intent explicit (no ALLY or hostile).
        condition_tmpl = ConditionTemplateFactory()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition_tmpl,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=0,
        )
        grant_technique(self.caster, technique)

        with self.assertRaises(InvalidCastTarget):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                target_persona=self.target,
                technique=technique,
            )


# ---------------------------------------------------------------------------
# FILTERED_GROUP standalone cast — #1321
# ---------------------------------------------------------------------------


@tag("postgres")
class TestFilteredGroupBenignCast(CastScenarioMixin):
    """FILTERED_GROUP benign capability buff applies to exactly the picked subset (#1321)."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # A third ally in the scene who is NOT in the supplied list.
        cls.third_ally = PersonaFactory()
        CharacterVitals.objects.create(
            character_sheet=cls.third_ally.character_sheet,
            health=50,
            max_health=50,
            base_max_health=50,
        )
        CharacterAnimaFactory(
            character=cls.third_ally.character_sheet.character,
            current=20,
            maximum=30,
        )
        # Add all three non-caster personas to the scene via Interaction rows so
        # _collect_scene_personas finds them.
        InteractionFactory(persona=cls.target, scene=cls.scene)
        InteractionFactory(persona=cls.third_ally, scene=cls.scene)

    def _make_filtered_group_ally_technique(self):
        """FILTERED_GROUP, ALLY condition, non-hostile, no behavior-altering."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
            target_type=ActionTargetType.FILTERED_GROUP,
        )
        condition_tmpl = ConditionTemplateFactory()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition_tmpl,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=0,
        )
        return technique, condition_tmpl

    def test_filtered_group_applies_to_picked_subset_only(self) -> None:
        """Picked subset [target, caster] → target + caster get condition; third_ally does not."""
        technique, condition_tmpl = self._make_filtered_group_ally_technique()
        grant_technique(self.caster, technique)

        # All characters in the scene so _collect_scene_personas finds them.
        for persona in (self.caster, self.target, self.third_ally):
            char = persona.character_sheet.character
            char.location = self.scene.location
            char.save()

        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success):
            cast = request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
                supplied_personas=[self.target, self.caster],
            )

        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)

        target_char = self.target.character_sheet.character
        third_char = self.third_ally.character_sheet.character
        self.assertTrue(
            get_active_conditions(target_char, condition=condition_tmpl).exists(),
            "target (in supplied list) must receive the ALLY condition.",
        )
        self.assertFalse(
            get_active_conditions(third_char, condition=condition_tmpl).exists(),
            "third_ally (NOT in supplied list) must NOT receive the condition.",
        )


# ---------------------------------------------------------------------------
# AREA technique consent guard — #1321
# ---------------------------------------------------------------------------


class TestAreaBehaviorAlteringCastRaises(CastScenarioMixin):
    """Behavior-altering AREA technique raises InvalidCastTarget (consent hole fix, #1321)."""

    def test_behavior_altering_area_cast_raises(self) -> None:
        """AREA technique with alters_behavior=True condition → InvalidCastTarget."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
            target_type=ActionTargetType.AREA,
        )
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        with self.assertRaises(InvalidCastTarget):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
            )

    def test_capability_area_cast_does_not_raise(self) -> None:
        """Non-behavior-altering (capability/stat) AREA technique does NOT raise."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
            target_type=ActionTargetType.AREA,
        )
        # ALLY condition whose category does NOT alter behavior → consent-free.
        condition_tmpl = ConditionTemplateFactory()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition_tmpl,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=0,
        )
        grant_technique(self.caster, technique)

        # Should not raise — just verifying no InvalidCastTarget is thrown.
        try:
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
            )
        except InvalidCastTarget as exc:
            self.fail(f"Capability AREA cast should not raise InvalidCastTarget: {exc}")


class TestFilteredGroupDeferredCases(CastScenarioMixin):
    """FILTERED_GROUP hostile and behavior-altering paths raise InvalidCastTarget (#1321)."""

    def test_hostile_filtered_group_with_supplied_personas_raises(self) -> None:
        """Hostile FILTERED_GROUP cast with supplied_personas → InvalidCastTarget (deferred)."""
        # Hostile technique: default TechniqueFactory has base_power > 0 → damage profile.
        technique = TechniqueFactory(
            action_template=ActionTemplateFactory(),
            target_type=ActionTargetType.FILTERED_GROUP,
        )
        grant_technique(self.caster, technique)

        with self.assertRaises(InvalidCastTarget):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
                supplied_personas=[self.target],
            )

    def test_behavior_altering_filtered_group_with_supplied_personas_raises(self) -> None:
        """Behavior-altering FILTERED_GROUP + supplied_personas → InvalidCastTarget (deferred)."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
            target_type=ActionTargetType.FILTERED_GROUP,
        )
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        with self.assertRaises(InvalidCastTarget):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
                supplied_personas=[self.target],
            )
