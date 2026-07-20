"""Tests for Miracle models and divine intervention (#2360)."""

from django.test import TestCase

from world.worship.constants import MiracleTrigger
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import (
    DivineInterventionConfig,
    Miracle,
    MiraclePerformance,
)
from world.worship.services import get_divine_intervention_config, spend_worship_pool


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


class SpendWorshipPoolTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.being.resonance_pool = 500
        cls.being.save()

    def test_succeeds_when_sufficient(self) -> None:
        result = spend_worship_pool(self.being, 100, reason="test")
        self.assertTrue(result)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 400)

    def test_fails_when_insufficient(self) -> None:
        result = spend_worship_pool(self.being, 600, reason="test")
        self.assertFalse(result)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 500)

    def test_rejects_non_positive(self) -> None:
        with self.assertRaises(ValueError):
            spend_worship_pool(self.being, 0)

    def test_get_config_creates_singleton(self) -> None:
        DivineInterventionConfig.objects.all().delete()
        cfg = get_divine_intervention_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(cfg.favor_threshold, 50)
