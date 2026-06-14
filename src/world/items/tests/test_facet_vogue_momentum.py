"""Tests for the FacetVogueMomentum model (#514)."""

from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.items.factories import FacetVogueMomentumFactory
from world.items.models import FacetVogueMomentum
from world.magic.factories import FacetFactory
from world.societies.factories import SocietyFactory


class FacetVogueMomentumModelTests(TestCase):
    """Cover FacetVogueMomentum defaults, unique constraint, ordering, and str."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory()
        cls.facet = FacetFactory()

    def test_points_default_zero(self) -> None:
        """points defaults to 0."""
        momentum = FacetVogueMomentumFactory(society=self.society, facet=self.facet)
        self.assertEqual(momentum.points, 0)

    def test_str(self) -> None:
        """__str__ returns expected format."""
        momentum = FacetVogueMomentumFactory(society=self.society, facet=self.facet)
        expected = f"FacetVogueMomentum({self.society.pk}/{self.facet.pk}=0)"
        self.assertEqual(str(momentum), expected)

    def test_unique_per_society_and_facet(self) -> None:
        """Duplicate (society, facet) raises IntegrityError."""
        FacetVogueMomentumFactory(society=self.society, facet=self.facet)
        with self.assertRaises(IntegrityError):
            FacetVogueMomentumFactory(society=self.society, facet=self.facet)

    def test_ordering_by_points_descending(self) -> None:
        """Default ordering is -points (highest momentum first)."""
        facet_low = FacetFactory()
        facet_high = FacetFactory()
        low = FacetVogueMomentumFactory(society=self.society, facet=facet_low, points=1)
        high = FacetVogueMomentumFactory(society=self.society, facet=facet_high, points=99)
        qs = list(FacetVogueMomentum.objects.filter(society=self.society))
        self.assertEqual(qs[0], high)
        self.assertEqual(qs[1], low)

    def test_factory_creates_valid_row(self) -> None:
        """FacetVogueMomentumFactory creates a valid row with default subfactories."""
        momentum = FacetVogueMomentumFactory()
        self.assertIsNotNone(momentum.pk)
        self.assertIsNotNone(momentum.society_id)
        self.assertIsNotNone(momentum.facet_id)
        self.assertEqual(momentum.points, 0)
