"""Authoring rules on ``VowAddedEffect`` and its payload children (#4581).

A rule that reads a child lives on the child and reads ``self.effect``, because
the admin validates a header form before its inline rows exist.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
from world.covenants.constants import VowEffectContext, VowEffectFrequency
from world.covenants.factories import (
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectDamageProfileFactory,
    VowAddedEffectFactory,
    VowAddedEffectRemovedConditionFactory,
)
from world.covenants.perks.constants import Situation
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
    TechniqueRemovedConditionFactory,
)


class VowAddedEffectCleanTests(TestCase):
    """The header's rules."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory()

    def _keys(self, row: object) -> set[str]:
        with self.assertRaises(ValidationError) as caught:
            row.full_clean()  # type: ignore[attr-defined]
        return set(caught.exception.message_dict)

    def test_a_limited_frequency_needs_a_fight(self) -> None:
        for context in (VowEffectContext.ANY, VowEffectContext.OUT_OF_COMBAT):
            for frequency in (VowEffectFrequency.ONCE_PER_ROUND, VowEffectFrequency.ONCE_PER_FIGHT):
                row = VowAddedEffectFactory.build(
                    covenant_role=self.role, cast_context=context, frequency=frequency
                )
                self.assertIn("frequency", self._keys(row))

    def test_a_limited_frequency_in_combat_is_clean(self) -> None:
        row = VowAddedEffectFactory.build(
            covenant_role=self.role,
            cast_context=VowEffectContext.IN_COMBAT,
            frequency=VowEffectFrequency.ONCE_PER_ROUND,
        )
        row.full_clean(exclude=["covenant_role"])

    def test_a_narrowing_technique_must_carry_the_function(self) -> None:
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.STRIKE)
        row = VowAddedEffectFactory.build(
            covenant_role=self.role, function=TechniqueFunction.HOLD, technique=technique
        )
        self.assertIn("technique", self._keys(row))

    def test_a_narrowing_technique_that_carries_the_function_is_clean(self) -> None:
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.HOLD)
        row = VowAddedEffectFactory.build(
            covenant_role=self.role, function=TechniqueFunction.HOLD, technique=technique
        )
        row.full_clean()

    def test_gift_and_technique_together_are_refused_in_clean(self) -> None:
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.HOLD)
        row = VowAddedEffectFactory.build(
            covenant_role=self.role,
            function=TechniqueFunction.HOLD,
            gift=GiftFactory(),
            technique=technique,
        )
        self.assertIn("technique", self._keys(row))

    def test_an_upgrade_must_share_the_function(self) -> None:
        base = VowAddedEffectFactory(covenant_role=self.role, function=TechniqueFunction.HOLD)
        row = VowAddedEffectFactory.build(
            covenant_role=self.role,
            function=TechniqueFunction.STRIKE,
            unlock_thread_level=3,
            upgrades=base,
        )
        self.assertIn("upgrades", self._keys(row))

    def test_an_upgrade_may_not_name_itself(self) -> None:
        row = VowAddedEffectFactory(covenant_role=self.role, unlock_thread_level=4)
        row.upgrades = row
        self.assertIn("upgrades", self._keys(row))

    def test_an_upgrade_on_the_same_role_must_unlock_later(self) -> None:
        base = VowAddedEffectFactory(covenant_role=self.role, unlock_thread_level=2)
        same = VowAddedEffectFactory.build(
            covenant_role=self.role, unlock_thread_level=2, upgrades=base
        )
        self.assertIn("upgrades", self._keys(same))
        later = VowAddedEffectFactory.build(
            covenant_role=self.role, unlock_thread_level=3, upgrades=base
        )
        later.full_clean()

    def test_an_upgrade_on_a_sub_role_may_name_the_parents_row(self) -> None:
        parent = CovenantRoleFactory()
        sub = SubroleCovenantRoleFactory(parent_role=parent)
        base = VowAddedEffectFactory(covenant_role=parent, unlock_thread_level=2)
        row = VowAddedEffectFactory.build(covenant_role=sub, unlock_thread_level=2, upgrades=base)
        row.full_clean()

    def test_an_upgrade_may_not_name_an_unrelated_roles_row(self) -> None:
        other = VowAddedEffectFactory(covenant_role=CovenantRoleFactory())
        row = VowAddedEffectFactory.build(
            covenant_role=self.role, unlock_thread_level=5, upgrades=other
        )
        self.assertIn("upgrades", self._keys(row))

    def test_a_saved_damage_child_pins_the_context(self) -> None:
        effect = VowAddedEffectFactory(cast_context=VowEffectContext.IN_COMBAT)
        VowAddedEffectDamageProfileFactory(effect=effect)
        effect.cast_context = VowEffectContext.ANY
        self.assertIn("cast_context", self._keys(effect))

    def test_an_effect_without_damage_children_may_change_context(self) -> None:
        effect = VowAddedEffectFactory(cast_context=VowEffectContext.IN_COMBAT)
        effect.cast_context = VowEffectContext.ANY
        effect.full_clean()

    def test_situation_params_follow_the_situation(self) -> None:
        row = VowAddedEffectFactory.build(
            covenant_role=self.role, situation=Situation.SURROUNDED, affinity="abyssal"
        )
        self.assertIn("affinity", self._keys(row))


class VowAddedEffectChildCleanTests(TestCase):
    """The children's rules."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect = VowAddedEffectFactory(cast_context=VowEffectContext.IN_COMBAT)

    def test_damage_needs_a_fight(self) -> None:
        effect = VowAddedEffectFactory(cast_context=VowEffectContext.ANY)
        with self.assertRaises(ValidationError):
            VowAddedEffectDamageProfileFactory.build(effect=effect).full_clean()

    def test_damage_in_a_fight_is_clean(self) -> None:
        VowAddedEffectDamageProfileFactory.build(effect=self.effect).full_clean()

    def test_a_behavior_altering_condition_is_refused(self) -> None:
        category = ConditionCategoryFactory(alters_behavior=True)
        row = VowAddedEffectAppliedConditionFactory.build(
            effect=self.effect, condition=ConditionTemplateFactory(category=category)
        )
        with self.assertRaises(ValidationError) as caught:
            row.full_clean()
        self.assertIn("condition", caught.exception.message_dict)

    def test_an_ordinary_condition_is_clean(self) -> None:
        category = ConditionCategoryFactory(alters_behavior=False)
        VowAddedEffectAppliedConditionFactory.build(
            effect=self.effect, condition=ConditionTemplateFactory(category=category)
        ).full_clean()

    def test_inert_removal_knobs_are_refused_on_both_removal_rows(self) -> None:
        rows = (
            VowAddedEffectRemovedConditionFactory.build(
                effect=self.effect, condition=ConditionTemplateFactory(), base_severity=3
            ),
            TechniqueRemovedConditionFactory.build(
                technique=TechniqueFactory(), condition=ConditionTemplateFactory(), base_severity=3
            ),
        )
        for row in rows:
            with self.assertRaises(ValidationError) as caught:
                row.full_clean()
            self.assertIn("base_severity", caught.exception.message_dict)

    def test_default_removal_knobs_are_clean(self) -> None:
        VowAddedEffectRemovedConditionFactory.build(
            effect=self.effect, condition=ConditionTemplateFactory()
        ).full_clean()
