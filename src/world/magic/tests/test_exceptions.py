"""Tests for magic app typed exceptions."""

from django.test import SimpleTestCase, TestCase

from world.magic.exceptions import (
    BilateralRoleConflictError,
    NoMatchingWornFacetItemsError,
    NotInitiatorError,
    NotInvitedError,
    ParticipantCountError,
    RequiredReferenceMissingError,
    SessionNotInPendingError,
    SessionTargetMissingError,
    ThresholdNotMetError,
)


class NoMatchingWornFacetItemsErrorTests(SimpleTestCase):
    def test_user_message(self) -> None:
        exc = NoMatchingWornFacetItemsError()
        self.assertEqual(exc.user_message, "You aren't wearing anything bearing this facet.")


class RitualSessionErrorTests(TestCase):
    """RitualSessionError family — user_message in SAFE_MESSAGES validation."""

    def test_ritual_session_error_user_message_in_safe_messages(self) -> None:
        """Each typed exception's user_message must be in its SAFE_MESSAGES."""
        for cls in [
            SessionNotInPendingError,
            ThresholdNotMetError,
            RequiredReferenceMissingError,
            SessionTargetMissingError,
            NotInvitedError,
            NotInitiatorError,
            BilateralRoleConflictError,
            ParticipantCountError,
        ]:
            with self.subTest(cls=cls.__name__):
                instance = cls()
                self.assertIn(
                    instance.user_message,
                    cls.SAFE_MESSAGES,
                    f"{cls.__name__} user_message not in SAFE_MESSAGES",
                )
