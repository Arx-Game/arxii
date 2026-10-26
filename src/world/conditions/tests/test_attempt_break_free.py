"""Tests for attempt_break_free service (#2706)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import BreakFreeMode
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import attempt_break_free
from world.conditions.types import BreakFreeOutcome


def _mock_check_result(success_level: int):
    """Build a mock CheckResult whose success_level property returns the given integer."""
    result = MagicMock()
    result.success_level = success_level
    return result


class AttemptBreakFreeTest(TestCase):
    def setUp(self):
        self.check_type = CheckTypeFactory()
        self.template = ConditionTemplateFactory(
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=self.check_type,
            break_free_difficulty=10,
        )
        self.instance = ConditionInstanceFactory(
            condition=self.template,
            severity=5,
            is_aware=True,
        )

    @patch("world.checks.services.perform_check")
    def test_critical_success_removes_condition(self, mock_check):
        """SL >= 2 removes the condition entirely."""
        mock_check.return_value = _mock_check_result(success_level=2)
        result = attempt_break_free(self.instance)
        self.assertTrue(result.broke_free)
        self.assertEqual(result.outcome, BreakFreeOutcome.SHATTERED)
        # The instance should be resolved (removed), so a fresh query returns nothing.
        self.assertFalse(ConditionInstance.objects.filter(pk=self.instance.pk).exists())

    @patch("world.checks.services.perform_check")
    def test_partial_success_decays_severity(self, mock_check):
        """SL == 1 reduces severity."""
        mock_check.return_value = _mock_check_result(success_level=1)
        result = attempt_break_free(self.instance)
        self.assertFalse(result.broke_free)
        self.assertEqual(result.outcome, BreakFreeOutcome.WEAKENED)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.severity, 4)  # 5 - 1

    @patch("world.checks.services.perform_check")
    def test_failure_does_nothing(self, mock_check):
        """SL == 0: no change."""
        mock_check.return_value = _mock_check_result(success_level=0)
        original_severity = self.instance.severity
        result = attempt_break_free(self.instance)
        self.assertFalse(result.broke_free)
        self.assertEqual(result.outcome, BreakFreeOutcome.HELD)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.severity, original_severity)

    @patch("world.checks.services.perform_check")
    def test_botch_advances_severity(self, mock_check):
        """SL <= -2: condition strengthens."""
        mock_check.return_value = _mock_check_result(success_level=-2)
        result = attempt_break_free(self.instance)
        self.assertFalse(result.broke_free)
        self.assertEqual(result.outcome, BreakFreeOutcome.STRENGTHENED)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.severity, 6)  # 5 + 1

    @patch("world.checks.services.perform_check")
    def test_rate_limited_out_of_combat(self, mock_check):
        """Out-of-combat: second attempt within cooldown window is blocked."""
        # Use a failure outcome (SL=0) so the instance survives the first attempt.
        mock_check.return_value = _mock_check_result(success_level=0)
        attempt_break_free(self.instance, in_combat_tick=False)
        self.instance.refresh_from_db()
        result = attempt_break_free(self.instance, in_combat_tick=False)
        self.assertFalse(result.attempted)

    @patch("world.checks.services.perform_check")
    def test_combat_tick_not_rate_limited(self, mock_check):
        """In combat: no rate-limit stamp, can attempt every tick."""
        mock_check.return_value = _mock_check_result(success_level=0)
        attempt_break_free(self.instance, in_combat_tick=True)
        self.instance.refresh_from_db()
        # last_resist_attempt_at should NOT be stamped in combat
        self.assertIsNone(self.instance.last_resist_attempt_at)
        # Second attempt in combat should work
        result = attempt_break_free(self.instance, in_combat_tick=True)
        self.assertTrue(result.attempted)

    @patch("world.checks.services.perform_check")
    def test_pending_rally_bonus_consumed(self, mock_check):
        """pending_rally_bonus is added to extra_modifiers and consumed."""
        self.instance.pending_rally_bonus = 15
        self.instance.save(update_fields=["pending_rally_bonus"])
        mock_check.return_value = _mock_check_result(success_level=0)
        attempt_break_free(self.instance)
        _, kwargs = mock_check.call_args
        self.assertEqual(kwargs.get("extra_modifiers"), 15)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.pending_rally_bonus, 0)

    def test_unaware_target_blocked(self):
        """is_aware=False blocks self-initiated break-free."""
        self.instance.is_aware = False
        self.instance.save(update_fields=["is_aware"])
        result = attempt_break_free(self.instance)
        self.assertFalse(result.attempted)
        self.assertIn("notice", result.message.lower())

    @patch("world.checks.services.perform_check")
    def test_none_mode_blocked(self, mock_check):
        """break_free_mode=NONE blocks attempts."""
        self.template.break_free_mode = BreakFreeMode.NONE
        self.template.save(update_fields=["break_free_mode"])
        result = attempt_break_free(self.instance)
        self.assertFalse(result.attempted)
        mock_check.assert_not_called()

    @patch("world.checks.services.perform_check")
    def test_caster_level_adds_difficulty(self, mock_check):
        """When source_character is set, level_opposition adds difficulty."""
        caster = ObjectDBFactory()
        CharacterSheetFactory(character=caster)
        self.instance.source_character = caster
        self.instance.save(update_fields=["source_character"])
        mock_check.return_value = _mock_check_result(success_level=0)
        attempt_break_free(self.instance)
        _, kwargs = mock_check.call_args
        # difficulty should be > base (10) because of caster level opposition
        self.assertGreater(kwargs.get("target_difficulty"), 10)

    @patch("world.checks.services.perform_check")
    def test_no_caster_uses_base_difficulty(self, mock_check):
        """When source_character is None, difficulty = base only."""
        mock_check.return_value = _mock_check_result(success_level=0)
        attempt_break_free(self.instance)
        _, kwargs = mock_check.call_args
        self.assertEqual(kwargs.get("target_difficulty"), 10)

    @patch("world.checks.services.perform_check")
    def test_level_override_forwarded(self, mock_check):
        """level_override is forwarded to perform_check."""
        mock_check.return_value = _mock_check_result(success_level=0)
        attempt_break_free(self.instance, level_override=20)
        _, kwargs = mock_check.call_args
        self.assertEqual(kwargs.get("level_override"), 20)

    @patch("world.checks.services.perform_check")
    def test_helper_bonus_added(self, mock_check):
        """helper_bonus is added to extra_modifiers."""
        mock_check.return_value = _mock_check_result(success_level=0)
        attempt_break_free(self.instance, helper_bonus=10)
        _, kwargs = mock_check.call_args
        self.assertEqual(kwargs.get("extra_modifiers"), 10)
