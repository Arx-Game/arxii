"""Tests for the synergy narration clause (#2018)."""

from __future__ import annotations

from django.test import TestCase

from world.combat.interaction_services import synergy_clause
from world.conditions.factories import (
    ConditionDamageInteractionFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.types import DamageInteractionResult


class SynergyClauseTests(TestCase):
    """Tests for synergy_clause — the transition-only narration beat."""

    def setUp(self):
        self.frozen = ConditionTemplateFactory(name="Frozen")
        self.wet = ConditionTemplateFactory(name="Wet")
        self.force = DamageTypeFactory(name="Force-test-narration")
        self.fire = DamageTypeFactory(name="Fire-test-narration")

    def test_none_when_no_interaction(self):
        """No interaction result → no clause."""
        self.assertIsNone(synergy_clause(None))

    def test_none_when_modifier_only_no_transition(self):
        """A modifier-only interaction with no removal/apply → silent (no spam)."""
        interaction = ConditionDamageInteractionFactory(
            condition=self.wet,
            damage_type=self.fire,
            damage_modifier_percent=-30,
            removes_condition=False,
            applies_condition=None,
        )
        result = DamageInteractionResult(
            damage_modifier_percent=-30,
            fired_interactions=[interaction],
        )
        self.assertIsNone(synergy_clause(result))

    def test_authored_snippet_on_removal(self):
        """Authored narration_snippet is used when a condition is removed."""
        interaction = ConditionDamageInteractionFactory(
            condition=self.frozen,
            damage_type=self.force,
            damage_modifier_percent=50,
            removes_condition=True,
            narration_snippet="the frozen shell shatters under the blow",
        )
        result = DamageInteractionResult(
            damage_modifier_percent=50,
            fired_interactions=[interaction],
        )
        clause = synergy_clause(result)
        self.assertIsNotNone(clause)
        self.assertIn("the frozen shell shatters under the blow", clause)

    def test_composed_fallback_on_removal(self):
        """No authored snippet → composed fallback from condition name."""
        interaction = ConditionDamageInteractionFactory(
            condition=self.frozen,
            damage_type=self.force,
            damage_modifier_percent=50,
            removes_condition=True,
            narration_snippet="",
        )
        result = DamageInteractionResult(
            damage_modifier_percent=50,
            fired_interactions=[interaction],
        )
        clause = synergy_clause(result)
        self.assertIsNotNone(clause)
        self.assertIn("Frozen", clause)
        self.assertIn("shatters", clause)

    def test_modifier_appended_on_transition(self):
        """When a transition occurs with a non-zero modifier, the modifier is appended."""
        interaction = ConditionDamageInteractionFactory(
            condition=self.frozen,
            damage_type=self.force,
            damage_modifier_percent=50,
            removes_condition=True,
            narration_snippet="the frozen shell shatters",
        )
        result = DamageInteractionResult(
            damage_modifier_percent=50,
            fired_interactions=[interaction],
        )
        clause = synergy_clause(result)
        self.assertIn("+50%", clause)
