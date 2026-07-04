"""Tests for the DistinctionResonanceGrant model (#1834).

DistinctionResonanceGrant is the authoring surface for the currency knobs a
Distinction grants in a Resonance: a flat seed amount and an earn-rate bonus,
both rank-scaled by the character's rank in the distinction.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.distinctions.factories import DistinctionFactory
from world.magic.factories import DistinctionResonanceGrantFactory, ResonanceFactory
from world.magic.models import DistinctionResonanceGrant


class DistinctionResonanceGrantModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.distinction = DistinctionFactory(name="Silver Tongue")
        cls.resonance = ResonanceFactory(name="Bene")

    def test_create_via_factory_persists_fields(self):
        grant = DistinctionResonanceGrantFactory(
            distinction=self.distinction,
            resonance=self.resonance,
            flat_amount_per_rank=5,
            earn_rate_bonus_per_rank=Decimal("1.50"),
        )
        grant.refresh_from_db()
        self.assertEqual(grant.distinction, self.distinction)
        self.assertEqual(grant.resonance, self.resonance)
        self.assertEqual(grant.flat_amount_per_rank, 5)
        self.assertEqual(grant.earn_rate_bonus_per_rank, Decimal("1.50"))

    def test_defaults(self):
        grant = DistinctionResonanceGrant.objects.create(
            distinction=self.distinction,
            resonance=self.resonance,
        )
        self.assertEqual(grant.flat_amount_per_rank, 0)
        self.assertEqual(grant.earn_rate_bonus_per_rank, Decimal(0))

    def test_unique_per_distinction_and_resonance(self):
        DistinctionResonanceGrant.objects.create(
            distinction=self.distinction,
            resonance=self.resonance,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DistinctionResonanceGrant.objects.create(
                distinction=self.distinction,
                resonance=self.resonance,
            )

    def test_earn_rate_bonus_over_max_fails_full_clean(self):
        grant = DistinctionResonanceGrant.objects.create(
            distinction=self.distinction,
            resonance=self.resonance,
            earn_rate_bonus_per_rank=Decimal("6.00"),
        )
        with self.assertRaises(ValidationError):
            grant.full_clean()

    def test_earn_rate_bonus_at_max_passes_full_clean(self):
        grant = DistinctionResonanceGrant.objects.create(
            distinction=self.distinction,
            resonance=self.resonance,
            earn_rate_bonus_per_rank=Decimal("5.00"),
        )
        grant.full_clean()  # should not raise

    def test_str(self):
        grant = DistinctionResonanceGrant.objects.create(
            distinction=self.distinction,
            resonance=self.resonance,
        )
        self.assertEqual(str(grant), f"{self.distinction} grants {self.resonance}")
