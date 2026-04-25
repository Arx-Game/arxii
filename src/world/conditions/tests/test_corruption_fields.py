"""Tests for Scope 7 corruption fields added to ConditionStage and ConditionTemplate."""

from django.test import TestCase

from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.types import AdvancementResistFailureKind


class TestConditionTemplateCorruptionResonance(TestCase):
    def test_default_is_null(self):
        template = ConditionTemplateFactory()
        self.assertIsNone(template.corruption_resonance)


class TestConditionStageAdvancementFailureKind(TestCase):
    def test_default_is_advance_at_threshold(self):
        stage = ConditionStageFactory()
        self.assertEqual(
            stage.advancement_resist_failure_kind,
            AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
        )
