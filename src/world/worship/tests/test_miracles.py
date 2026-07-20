"""Tests for Miracle models and divine intervention (#2360)."""

from django.test import TestCase

from world.worship.constants import MiracleTrigger
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import (
    DivineInterventionConfig,
    Miracle,
    MiraclePerformance,
)


class MiracleModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.miracle = Miracle.objects.create(
            name="Test Aegis",
            being=cls.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.INCAPACITATED,
            favor_threshold=50,
            narrative_text="A divine shield flares.",
        )

    def test_miracle_str(self) -> None:
        self.assertIn("Test Aegis", str(self.miracle))

    def test_unique_name_per_being(self) -> None:
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Miracle.objects.create(
                name="Test Aegis",
                being=self.being,
                resonance_pool_cost=50,
                intervention_trigger=MiracleTrigger.INCAPACITATED,
                narrative_text="dup",
            )

    def test_divine_intervention_config_defaults(self) -> None:
        cfg = DivineInterventionConfig.objects.create()
        self.assertEqual(cfg.favor_threshold, 50)
        self.assertEqual(cfg.cooldown_hours, 24)
        self.assertEqual(cfg.min_pool_for_intervention, 100)

    def test_miracle_performance_str(self) -> None:
        perf = MiraclePerformance.objects.create(
            miracle=self.miracle,
            being=self.being,
            resonance_spent=100,
            trigger_event="character_incapacitated",
        )
        self.assertIn("Test Aegis", str(perf))
