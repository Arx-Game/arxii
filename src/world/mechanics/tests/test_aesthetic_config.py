"""Tests for AestheticAxisConfig singleton and its lazy getter."""

from decimal import Decimal

from django.test import TestCase

from world.mechanics.models import AestheticAxisConfig
from world.mechanics.services import get_aesthetic_config


class AestheticAxisConfigGetterTests(TestCase):
    """Test get_aesthetic_config() lazy-creates and returns the pk=1 singleton."""

    def test_lazy_creates_pk1_with_defaults(self) -> None:
        """get_aesthetic_config() creates pk=1 when the row does not exist."""
        config = get_aesthetic_config()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.base_magnitude, 5)
        self.assertEqual(config.full_combination_bonus, Decimal("1.50"))

    def test_second_call_returns_same_row(self) -> None:
        """A second call returns the existing row; no duplicate is created."""
        first = get_aesthetic_config()
        second = get_aesthetic_config()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AestheticAxisConfig.objects.count(), 1)
