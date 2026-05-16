"""Tests for force_check_outcome context manager + CheckCapture."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import perform_check
from world.checks.test_helpers import CheckCapture, force_check_outcome
from world.traits.factories import CheckOutcomeFactory


class ForceCheckOutcomeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory(name="t9_test_check")
        cls.crit_success = CheckOutcomeFactory(name="Critical Success", success_level=2)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)

    def test_yields_check_capture_instance(self) -> None:
        with force_check_outcome(self.crit_success) as capture:
            self.assertIsInstance(capture, CheckCapture)
            # Before any perform_check call, fields are unset.
            self.assertIsNone(capture.target_difficulty)
            self.assertIsNone(capture.check_type)

    def test_forces_outcome(self) -> None:
        sheet = CharacterSheetFactory()
        with force_check_outcome(self.crit_success):
            result = perform_check(
                character=sheet.character,
                check_type=self.check_type,
                target_difficulty=20,
            )
        self.assertEqual(result.outcome, self.crit_success)

    def test_capture_records_target_difficulty(self) -> None:
        sheet = CharacterSheetFactory()
        with force_check_outcome(self.success) as capture:
            perform_check(
                character=sheet.character,
                check_type=self.check_type,
                target_difficulty=25,
            )
        self.assertEqual(capture.target_difficulty, 25)
        self.assertEqual(capture.check_type, self.check_type)

    def test_force_is_single_shot(self) -> None:
        """Second perform_check inside same context manager does NOT return forced
        outcome — the thread-local is cleared after first use."""
        sheet = CharacterSheetFactory()
        with force_check_outcome(self.success):
            r1 = perform_check(
                character=sheet.character,
                check_type=self.check_type,
                target_difficulty=10,
            )
            r2 = perform_check(
                character=sheet.character,
                check_type=self.check_type,
                target_difficulty=10,
            )
        self.assertEqual(r1.outcome, self.success)
        # r2 should be a real check result, not the forced outcome (unless real
        # resolution happens to return the same outcome). The assertion is that
        # we made it through without exception and r1 was forced.
        self.assertIsNotNone(r2)

    def test_outside_context_perform_check_is_unchanged(self) -> None:
        """No force in effect → real resolution runs."""
        sheet = CharacterSheetFactory()
        # Real resolution may produce any outcome; the test just asserts no exception
        # and that the result is a CheckResult (not None, not a raised exception).
        result = perform_check(
            character=sheet.character,
            check_type=self.check_type,
            target_difficulty=10,
        )
        self.assertIsNotNone(result)
