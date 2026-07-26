"""Tests that perform_check threads level_override to the breakdown (#2706)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import _CheckBreakdown, perform_check

_MOCK_BREAKDOWN = _CheckBreakdown(
    trait_points=0,
    specialization_points=0,
    aspect_bonus=0,
    level_points=75,
    capability_points=0,
    total_points=10,
    roller_rank=None,
    target_rank=None,
    rank_difference=0,
    chart=None,
)


class PerformCheckLevelOverrideTest(TestCase):
    def setUp(self):
        self.character = ObjectDBFactory()
        CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory()

    @patch("world.checks.services._compute_check_breakdown")
    def test_level_override_forwarded_to_breakdown(self, mock_breakdown):
        """perform_check passes level_override to _compute_check_breakdown."""
        mock_breakdown.return_value = _MOCK_BREAKDOWN
        with patch("world.checks.services.get_rollmod", return_value=0):
            perform_check(self.character, self.check_type, level_override=15)
        _, kwargs = mock_breakdown.call_args
        self.assertEqual(kwargs.get("level_override"), 15)

    @patch("world.checks.services._compute_check_breakdown")
    def test_level_override_none_by_default(self, mock_breakdown):
        """perform_check defaults level_override to None (byte-identical to before)."""
        mock_breakdown.return_value = _MOCK_BREAKDOWN
        with patch("world.checks.services.get_rollmod", return_value=0):
            perform_check(self.character, self.check_type)
        _, kwargs = mock_breakdown.call_args
        self.assertIsNone(kwargs.get("level_override"))

    @patch("world.checks.services._compute_check_breakdown")
    def test_level_override_forwarded_on_forced_outcome_path(self, mock_breakdown):
        """The forced-outcome test seam also forwards level_override."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        mock_breakdown.return_value = _MOCK_BREAKDOWN
        outcome = CheckOutcomeFactory(success_level=0)
        with patch("world.checks.services.get_rollmod", return_value=0):
            with force_check_outcome(outcome):
                perform_check(self.character, self.check_type, level_override=20)
        _, kwargs = mock_breakdown.call_args
        self.assertEqual(kwargs.get("level_override"), 20)
