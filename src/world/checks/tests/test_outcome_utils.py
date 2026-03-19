"""Tests for shared outcome utilities."""

from dataclasses import dataclass
from unittest.mock import patch

from django.test import TestCase

from world.checks.outcome_utils import (
    build_outcome_display,
    filter_character_loss,
    select_weighted,
)
from world.checks.types import OutcomeDisplay


@dataclass
class FakeOutcome:
    """Minimal duck-typed outcome for testing shared utilities."""

    label: str
    weight: int
    character_loss: bool = False
    pk: int | None = None


@dataclass
class FakeTier:
    """Minimal outcome tier with a name attribute."""

    name: str


@dataclass
class FakeOutcomeWithTier:
    """Fake outcome with an outcome_tier for roulette display tests."""

    label: str
    weight: int
    outcome_tier: FakeTier
    pk: int | None = None


class SelectWeightedTests(TestCase):
    """Tests for select_weighted()."""

    def test_single_item_returns_it(self) -> None:
        item = FakeOutcome(label="only", weight=1)
        result = select_weighted([item])
        assert result is item

    def test_zero_weight_treated_as_one(self) -> None:
        """Items with weight=0 are treated as weight=1 to avoid errors."""
        item = FakeOutcome(label="zero", weight=0)
        result = select_weighted([item])
        assert result is item

    def test_multiple_items_returns_one(self) -> None:
        items = [
            FakeOutcome(label="a", weight=1),
            FakeOutcome(label="b", weight=99),
        ]
        result = select_weighted(items)
        assert result in items

    def test_heavily_weighted_item_selected_most_often(self) -> None:
        """With extreme weight difference, the heavy item dominates."""
        light = FakeOutcome(label="light", weight=1)
        heavy = FakeOutcome(label="heavy", weight=10000)
        results = [select_weighted([light, heavy]) for _ in range(100)]
        heavy_count = sum(1 for r in results if r is heavy)
        # With 10000:1 ratio, heavy should win nearly every time
        assert heavy_count >= 95


class FilterCharacterLossTests(TestCase):
    """Tests for filter_character_loss()."""

    @patch("world.checks.services.get_rollmod", return_value=0)
    def test_no_character_loss_returns_original(self, mock_rollmod: object) -> None:  # noqa: ARG002
        """Non-loss item is returned unchanged regardless of rollmod."""
        selected = FakeOutcome(label="safe", weight=5, character_loss=False)
        alternatives = [selected, FakeOutcome(label="other", weight=3)]
        # rollmod doesn't matter when character_loss is False
        result = filter_character_loss(None, selected, alternatives)  # type: ignore[arg-type]
        assert result is selected

    @patch("world.checks.services.get_rollmod", return_value=5)
    def test_positive_rollmod_swaps_to_alternative(self, mock_rollmod: object) -> None:  # noqa: ARG002
        """Character loss item is replaced when rollmod is positive."""
        loss_item = FakeOutcome(label="death", weight=10, character_loss=True)
        safe_item = FakeOutcome(label="safe", weight=3, character_loss=False)
        result = filter_character_loss(
            None,
            loss_item,
            [loss_item, safe_item],  # type: ignore[arg-type]
        )
        assert result is safe_item

    @patch("world.checks.services.get_rollmod", return_value=5)
    def test_no_alternatives_keeps_original(self, mock_rollmod: object) -> None:  # noqa: ARG002
        """When all alternatives also have character_loss, original stands."""
        loss_item = FakeOutcome(label="death", weight=10, character_loss=True)
        other_loss = FakeOutcome(label="worse_death", weight=5, character_loss=True)
        result = filter_character_loss(
            None,
            loss_item,
            [loss_item, other_loss],  # type: ignore[arg-type]
        )
        assert result is loss_item

    @patch("world.checks.services.get_rollmod", return_value=0)
    def test_zero_rollmod_keeps_loss(self, mock_rollmod: object) -> None:  # noqa: ARG002
        """Character loss stands when rollmod is zero."""
        loss_item = FakeOutcome(label="death", weight=10, character_loss=True)
        safe_item = FakeOutcome(label="safe", weight=3, character_loss=False)
        result = filter_character_loss(
            None,
            loss_item,
            [loss_item, safe_item],  # type: ignore[arg-type]
        )
        assert result is loss_item

    @patch("world.checks.services.get_rollmod", return_value=-2)
    def test_negative_rollmod_keeps_loss(self, mock_rollmod: object) -> None:  # noqa: ARG002
        """Character loss stands when rollmod is negative."""
        loss_item = FakeOutcome(label="death", weight=10, character_loss=True)
        safe_item = FakeOutcome(label="safe", weight=3, character_loss=False)
        result = filter_character_loss(
            None,
            loss_item,
            [loss_item, safe_item],  # type: ignore[arg-type]
        )
        assert result is loss_item

    @patch("world.checks.services.get_rollmod", return_value=5)
    def test_selects_lowest_weight_alternative(self, mock_rollmod: object) -> None:  # noqa: ARG002
        """Picks the worst (lowest weight) non-loss alternative."""
        loss_item = FakeOutcome(label="death", weight=10, character_loss=True)
        ok_item = FakeOutcome(label="ok", weight=5, character_loss=False)
        bad_item = FakeOutcome(label="bad", weight=1, character_loss=False)
        result = filter_character_loss(
            None,  # type: ignore[arg-type]
            loss_item,
            [loss_item, ok_item, bad_item],
        )
        assert result is bad_item


class BuildOutcomeDisplayTests(TestCase):
    """Tests for build_outcome_display()."""

    def test_empty_items_returns_selected_label(self) -> None:
        """When all_items is empty, returns single display from selected."""
        selected = FakeOutcome(label="fallback", weight=1)
        result = build_outcome_display([], selected)
        assert len(result) == 1
        assert result[0].is_selected is True
        assert result[0].label == "fallback"

    def test_marks_selected_by_pk(self) -> None:
        """Identifies the selected item by pk match."""
        tier = FakeTier(name="Success")
        items = [
            FakeOutcomeWithTier(label="A", weight=3, outcome_tier=tier, pk=1),
            FakeOutcomeWithTier(label="B", weight=7, outcome_tier=tier, pk=2),
        ]
        selected = items[1]
        result = build_outcome_display(items, selected)
        assert len(result) == 2
        assert result[0].is_selected is False
        assert result[1].is_selected is True
        assert result[1].label == "B"

    def test_marks_selected_by_label_when_no_pk(self) -> None:
        """Falls back to label matching when pk is None."""
        tier = FakeTier(name="Failure")
        items = [
            FakeOutcomeWithTier(label="X", weight=1, outcome_tier=tier, pk=None),
            FakeOutcomeWithTier(label="Y", weight=2, outcome_tier=tier, pk=None),
        ]
        selected = FakeOutcomeWithTier(label="Y", weight=2, outcome_tier=tier, pk=None)
        result = build_outcome_display(items, selected)
        selected_displays = [d for d in result if d.is_selected]
        assert len(selected_displays) == 1
        assert selected_displays[0].label == "Y"

    def test_returns_outcome_display_instances(self) -> None:
        tier = FakeTier(name="Neutral")
        items = [FakeOutcomeWithTier(label="Z", weight=5, outcome_tier=tier, pk=10)]
        result = build_outcome_display(items, items[0])
        assert isinstance(result[0], OutcomeDisplay)

    def test_tier_name_extracted_from_outcome_tier(self) -> None:
        tier = FakeTier(name="Critical")
        item = FakeOutcomeWithTier(label="Crit", weight=3, outcome_tier=tier, pk=1)
        result = build_outcome_display([item], item)
        assert result[0].tier_name == "Critical"

    def test_default_tier_name_when_no_outcome_tier(self) -> None:
        """Uses default_tier_name when item lacks outcome_tier."""
        item = FakeOutcome(label="Plain", weight=1, pk=1)
        result = build_outcome_display([item], item, default_tier_name="Fallback")
        assert result[0].tier_name == "Fallback"
