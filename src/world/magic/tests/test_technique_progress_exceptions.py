"""Tests for technique progress exceptions (#2711)."""

from django.test import TestCase

from world.magic.exceptions import (
    TechniqueProgressError,
    WeeklyTrainingCapExceeded,
)


class TechniqueProgressExceptionTests(TestCase):
    def test_technique_progress_error_has_user_message(self):
        exc = TechniqueProgressError("Custom message")
        self.assertEqual(exc.user_message, "Custom message")

    def test_technique_progress_error_default_message(self):
        exc = TechniqueProgressError()
        self.assertEqual(exc.user_message, "An error occurred with technique training.")

    def test_weekly_cap_exceeded_is_subclass(self):
        self.assertTrue(issubclass(WeeklyTrainingCapExceeded, TechniqueProgressError))

    def test_weekly_cap_exceeded_user_message(self):
        exc = WeeklyTrainingCapExceeded("You've trained enough this week.")
        self.assertEqual(exc.user_message, "You've trained enough this week.")

    def test_weekly_cap_exceeded_default_message(self):
        exc = WeeklyTrainingCapExceeded()
        self.assertEqual(exc.user_message, "You've trained as much as you can this week.")
