"""Tests for the worn_quality_aggregate helper (#1150).

Verifies that the helper correctly sums (item_quality * attachment_quality) for a
sequence of duck-typed rows exposing ``item_instance`` and
``attachment_quality_tier``.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from world.mechanics.services import worn_quality_aggregate


class _FakeTier:
    """Minimal quality-tier duck type: just stat_multiplier."""

    def __init__(self, stat_multiplier: float) -> None:
        self.stat_multiplier = stat_multiplier


class _FakeItem:
    def __init__(self, quality_tier: _FakeTier | None) -> None:
        self.quality_tier = quality_tier


class _FakeRow:
    def __init__(self, item_instance: _FakeItem, attachment_quality_tier: _FakeTier) -> None:
        self.item_instance = item_instance
        self.attachment_quality_tier = attachment_quality_tier


class WornQualityAggregateTests(SimpleTestCase):
    """Unit tests for worn_quality_aggregate."""

    def test_empty_rows_returns_zero(self) -> None:
        result = worn_quality_aggregate([])
        self.assertEqual(result, Decimal(0))

    def test_single_row_both_tiers_present(self) -> None:
        """item_mult=2.0, attach_mult=1.5 → 3.0."""
        row = _FakeRow(
            item_instance=_FakeItem(_FakeTier(2.0)),
            attachment_quality_tier=_FakeTier(1.5),
        )
        result = worn_quality_aggregate([row])
        self.assertEqual(result, Decimal("3.0"))

    def test_single_row_no_item_quality_tier_uses_one(self) -> None:
        """item.quality_tier is None → item_mult defaults to 1; attach_mult=1.5 → 1.5."""
        row = _FakeRow(
            item_instance=_FakeItem(quality_tier=None),
            attachment_quality_tier=_FakeTier(1.5),
        )
        result = worn_quality_aggregate([row])
        self.assertEqual(result, Decimal("1.5"))

    def test_two_rows_sums_products(self) -> None:
        """Two rows: (2.0 * 1.0) + (1.0 * 3.0) = 5.0."""
        rows = [
            _FakeRow(
                item_instance=_FakeItem(_FakeTier(2.0)),
                attachment_quality_tier=_FakeTier(1.0),
            ),
            _FakeRow(
                item_instance=_FakeItem(_FakeTier(1.0)),
                attachment_quality_tier=_FakeTier(3.0),
            ),
        ]
        result = worn_quality_aggregate(rows)
        self.assertEqual(result, Decimal("5.0"))

    def test_two_rows_known_tiers_expected_decimal_sum(self) -> None:
        """Regression: (1.2 * 0.8) + (1.0 * 1.0) = 0.96 + 1.0 = 1.96."""
        rows = [
            _FakeRow(
                item_instance=_FakeItem(_FakeTier(1.2)),
                attachment_quality_tier=_FakeTier(0.8),
            ),
            _FakeRow(
                item_instance=_FakeItem(_FakeTier(1.0)),
                attachment_quality_tier=_FakeTier(1.0),
            ),
        ]
        result = worn_quality_aggregate(rows)
        self.assertEqual(result, Decimal("1.96"))
