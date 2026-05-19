"""Tests for the Affordance lookup model (Phase 1, Task 1.1).

Affordance is a NaturalKey SharedMemoryModel lookup table mirroring the
``mechanics.ModifierCategory`` pattern: a unique ``name`` plus an optional
``description``. These tests assert round-trip persistence, the uniqueness
constraint, and natural-key serialization round-trip (the property fixtures
depend on).
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.missions.factories import AffordanceFactory
from world.missions.models import Affordance


class AffordanceModelTests(TestCase):
    """Round-trip, uniqueness, and natural-key behaviour."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.distraction = AffordanceFactory(name="distraction")

    def test_factory_round_trips(self) -> None:
        fetched = Affordance.objects.get(pk=self.distraction.pk)
        self.assertEqual(fetched.name, "distraction")
        self.assertEqual(str(fetched), "distraction")

    def test_name_is_unique(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Affordance.objects.create(name="distraction")

    def test_factory_get_or_create_returns_existing(self) -> None:
        again = AffordanceFactory(name="distraction")
        self.assertEqual(again.pk, self.distraction.pk)
        self.assertEqual(Affordance.objects.filter(name="distraction").count(), 1)

    def test_natural_key_round_trip(self) -> None:
        self.assertEqual(self.distraction.natural_key(), ("distraction",))
        resolved = Affordance.objects.get_by_natural_key("distraction")
        self.assertEqual(resolved.pk, self.distraction.pk)
