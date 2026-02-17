"""Tests for CGPointBudget model."""

from django.test import TestCase

from world.character_creation.models import CGPointBudget


class CGPointBudgetConversionRateTest(TestCase):
    """Test xp_conversion_rate field on CGPointBudget."""

    def test_default_conversion_rate(self):
        """Test default conversion rate is 2."""
        budget = CGPointBudget.objects.create(name="Test Budget", is_active=True)
        assert budget.xp_conversion_rate == 2

    def test_custom_conversion_rate(self):
        """Test setting custom conversion rate."""
        budget = CGPointBudget.objects.create(
            name="Test Budget",
            xp_conversion_rate=3,
            is_active=True,
        )
        assert budget.xp_conversion_rate == 3

    def test_get_active_conversion_rate_with_budget(self):
        """Test getting conversion rate from active budget."""
        CGPointBudget.objects.create(
            name="Active Budget",
            xp_conversion_rate=4,
            is_active=True,
        )
        assert CGPointBudget.get_active_conversion_rate() == 4

    def test_get_active_conversion_rate_default(self):
        """Test default conversion rate when no active budget exists."""
        assert CGPointBudget.get_active_conversion_rate() == 2
