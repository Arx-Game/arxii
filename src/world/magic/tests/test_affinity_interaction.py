"""Tests for AffinityInteraction directed-pair model (RA2).

Covers:
- Factory creates a valid row.
- Duplicate (source_affinity, environment_affinity) raises IntegrityError.
- severity_multiplier defaults to Decimal("1.00").
- str() contains both affinity names.
- Same source_affinity with different environment_affinity is allowed.
"""

from decimal import Decimal

from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase

from world.magic.factories import AffinityFactory, AffinityInteractionFactory


class AffinityInteractionFactoryTests(TestCase):
    """AffinityInteractionFactory creates valid rows."""

    def test_factory_creates_valid_row(self) -> None:
        row = AffinityInteractionFactory()
        self.assertIsNotNone(row.pk)
        self.assertIsNotNone(row.source_affinity_id)
        self.assertIsNotNone(row.environment_affinity_id)
        self.assertIsNotNone(row.valence)
        self.assertIsNotNone(row.kind)
        self.assertIsNotNone(row.aggressor)


class AffinityInteractionDefaultsTests(TestCase):
    """severity_multiplier defaults to 1.00."""

    def test_severity_multiplier_default(self) -> None:
        row = AffinityInteractionFactory()
        self.assertEqual(row.severity_multiplier, Decimal("1.00"))


class AffinityInteractionStrTests(TestCase):
    """__str__ contains both affinity names."""

    def test_str_contains_source_name(self) -> None:
        row = AffinityInteractionFactory()
        self.assertIn(row.source_affinity.name, str(row))

    def test_str_contains_environment_name(self) -> None:
        row = AffinityInteractionFactory()
        self.assertIn(row.environment_affinity.name, str(row))


class AffinityInteractionUniquePairTests(TestCase):
    """UniqueConstraint on (source_affinity, environment_affinity)."""

    def test_duplicate_pair_raises_integrity_error(self) -> None:
        source = AffinityFactory()
        env = AffinityFactory()
        AffinityInteractionFactory(source_affinity=source, environment_affinity=env)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AffinityInteractionFactory(source_affinity=source, environment_affinity=env)

    def test_same_source_different_environment_allowed(self) -> None:
        source = AffinityFactory()
        env_a = AffinityFactory()
        env_b = AffinityFactory()
        row_a = AffinityInteractionFactory(source_affinity=source, environment_affinity=env_a)
        row_b = AffinityInteractionFactory(source_affinity=source, environment_affinity=env_b)
        self.assertNotEqual(row_a.pk, row_b.pk)
