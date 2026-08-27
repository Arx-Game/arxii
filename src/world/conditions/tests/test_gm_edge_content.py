"""Tests for the Edge/Setback GM-fiat condition content (#3387)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.conditions.gm_edge_content import (
    EDGE_CONDITION_NAME,
    EDGE_MODIFIER_VALUE,
    SETBACK_CONDITION_NAME,
    SETBACK_MODIFIER_VALUE,
    ensure_gm_edge_content,
)
from world.conditions.models import ConditionCheckModifier, ConditionInstance, ConditionTemplate
from world.conditions.services import apply_condition, get_check_modifier


class EnsureGmEdgeContentTest(TestCase):
    def test_seed_creates_edge_and_setback_templates(self) -> None:
        ensure_gm_edge_content()
        edge = ConditionTemplate.objects.get(name=EDGE_CONDITION_NAME)
        setback = ConditionTemplate.objects.get(name=SETBACK_CONDITION_NAME)
        self.assertEqual(edge.default_duration_value, 1)
        self.assertEqual(setback.default_duration_value, 1)
        self.assertFalse(edge.category.is_negative)
        self.assertFalse(setback.category.is_negative)

    def test_seed_is_idempotent(self) -> None:
        ensure_gm_edge_content()
        ensure_gm_edge_content()
        self.assertEqual(ConditionTemplate.objects.filter(name=EDGE_CONDITION_NAME).count(), 1)
        self.assertEqual(ConditionTemplate.objects.filter(name=SETBACK_CONDITION_NAME).count(), 1)

    def test_check_modifier_skipped_without_combat_category(self) -> None:
        """No Combat CheckCategory authored — the modifier is skipped gracefully."""
        ensure_gm_edge_content()
        edge = ConditionTemplate.objects.get(name=EDGE_CONDITION_NAME)
        self.assertFalse(ConditionCheckModifier.objects.filter(condition=edge).exists())

    def test_check_modifier_attaches_when_combat_category_exists(self) -> None:
        CheckCategoryFactory(name="Combat")
        ensure_gm_edge_content()
        edge = ConditionTemplate.objects.get(name=EDGE_CONDITION_NAME)
        setback = ConditionTemplate.objects.get(name=SETBACK_CONDITION_NAME)
        edge_modifier = ConditionCheckModifier.objects.get(condition=edge)
        setback_modifier = ConditionCheckModifier.objects.get(condition=setback)
        self.assertEqual(edge_modifier.modifier_value, EDGE_MODIFIER_VALUE)
        self.assertEqual(setback_modifier.modifier_value, SETBACK_MODIFIER_VALUE)
        self.assertTrue(edge_modifier.scales_with_severity)
        self.assertTrue(setback_modifier.scales_with_severity)
        self.assertEqual(edge_modifier.check_category.name, "Combat")


class GmEdgeCheckModifierResolutionTest(TestCase):
    """Applied Edge/Setback resolve through get_check_modifier, the live perform_check path."""

    def setUp(self) -> None:
        self.combat_category = CheckCategoryFactory(name="Combat")
        self.check_type = CheckTypeFactory(category=self.combat_category)
        ensure_gm_edge_content()
        self.sheet = CharacterSheetFactory()

    def test_edge_gives_a_positive_modifier(self) -> None:
        edge = ConditionTemplate.objects.get(name=EDGE_CONDITION_NAME)
        apply_condition(self.sheet.character, edge, severity=1)
        result = get_check_modifier(self.sheet, self.check_type)
        self.assertEqual(result.total_modifier, EDGE_MODIFIER_VALUE)

    def test_setback_gives_a_negative_modifier(self) -> None:
        setback = ConditionTemplate.objects.get(name=SETBACK_CONDITION_NAME)
        apply_condition(self.sheet.character, setback, severity=1)
        result = get_check_modifier(self.sheet, self.check_type)
        self.assertEqual(result.total_modifier, SETBACK_MODIFIER_VALUE)

    def test_duration_rounds_round_trips_through_apply_condition(self) -> None:
        edge = ConditionTemplate.objects.get(name=EDGE_CONDITION_NAME)
        result = apply_condition(self.sheet.character, edge, severity=1)
        self.assertTrue(result.success, result.message)
        instance = ConditionInstance.objects.get(target=self.sheet.character, condition=edge)
        self.assertEqual(instance.rounds_remaining, 1)
