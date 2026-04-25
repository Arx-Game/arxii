"""Tests for CorruptionError and ProtagonismLockedError (Scope #7)."""

from django.test import TestCase

from world.magic.exceptions import CorruptionError, ProtagonismLockedError


class CorruptionErrorTests(TestCase):
    """CorruptionError base class behaviour."""

    def test_default_user_message(self) -> None:
        error = CorruptionError()
        self.assertEqual(error.user_message, "Corruption operation failed.")

    def test_default_message_in_safe_messages(self) -> None:
        error = CorruptionError()
        self.assertIn(error.user_message, CorruptionError.SAFE_MESSAGES)

    def test_custom_message_overrides(self) -> None:
        error = CorruptionError("custom message")
        self.assertEqual(error.user_message, "custom message")

    def test_is_exception(self) -> None:
        self.assertTrue(issubclass(CorruptionError, Exception))


class ProtagonismLockedErrorTests(TestCase):
    """ProtagonismLockedError typed exception."""

    def test_default_user_message_in_safe_messages(self) -> None:
        error = ProtagonismLockedError()
        self.assertIn(error.user_message, ProtagonismLockedError.SAFE_MESSAGES)

    def test_is_corruption_error_subclass(self) -> None:
        self.assertTrue(issubclass(ProtagonismLockedError, CorruptionError))

    def test_raises_correctly(self) -> None:
        with self.assertRaises(ProtagonismLockedError):
            raise ProtagonismLockedError

    def test_also_catchable_as_corruption_error(self) -> None:
        with self.assertRaises(CorruptionError):
            raise ProtagonismLockedError
