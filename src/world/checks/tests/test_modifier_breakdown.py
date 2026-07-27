"""Tests for modifier provenance dataclasses."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierBreakdown, ModifierContribution


class ModifierBreakdownTests(TestCase):
    """Test ModifierBreakdown totals and source provenance."""

    def test_modifier_breakdown_totals_and_lists_sources(self):
        b = ModifierBreakdown(
            contributions=[
                ModifierContribution(ModifierSourceKind.CONDITION, "Wounded (severe)", -4),
                ModifierContribution(ModifierSourceKind.ROLLMOD, "Roll modifier", 2),
            ]
        )
        assert b.total == -2
        assert [c.source_label for c in b.contributions] == ["Wounded (severe)", "Roll modifier"]


class PerformCheckWithModifiersExtraContributionsTests(TestCase):
    """Test extra_contributions forwarding and skip_fashion on the wrapper."""

    def test_sheet_less_actor_sums_extra_contributions_into_extra_modifiers(self):
        """A sheet-less actor's extra_contributions are summed into extra_modifiers."""
        character = MagicMock()
        character.character_sheet = None
        contributions = [
            ModifierContribution(ModifierSourceKind.EFFORT, "Caller", 5),
            ModifierContribution(ModifierSourceKind.EFFORT, "Rally", 3),
        ]
        with patch("world.checks.services.perform_check") as mock_perform:
            from world.checks.services import perform_check_with_modifiers

            perform_check_with_modifiers(
                character,
                MagicMock(),
                extra_modifiers=2,
                extra_contributions=contributions,
            )
            # extra_modifiers (2) + sum of contributions (8) = 10
            assert mock_perform.call_args.kwargs["extra_modifiers"] == 10

    def test_sheet_less_actor_without_extra_contributions_unchanged(self):
        """A sheet-less actor with no extra_contributions forwards extra_modifiers unchanged."""
        character = MagicMock()
        character.character_sheet = None
        with patch("world.checks.services.perform_check") as mock_perform:
            from world.checks.services import perform_check_with_modifiers

            perform_check_with_modifiers(
                character,
                MagicMock(),
                extra_modifiers=7,
            )
            assert mock_perform.call_args.kwargs["extra_modifiers"] == 7
