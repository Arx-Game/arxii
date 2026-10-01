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
    TechniqueRequirementsNotMet,
    ThresholdNotMetError,
)


class NoMatchingWornFacetItemsErrorTests(SimpleTestCase):
    def test_user_message(self) -> None:
        exc = NoMatchingWornFacetItemsError()
        self.assertEqual(exc.user_message, "You aren't wearing anything bearing this facet.")


class TechniqueRequirementsNotMetTests(SimpleTestCase):
    """``user_message`` lists the failed requirement messages (#4097 fix round 2,
    mirrors ``PathRequirementsNotMet``)."""

    def test_user_message_lists_single_failure(self) -> None:
        exc = TechniqueRequirementsNotMet(["Need to know Thornweave"])
        self.assertEqual(
            exc.user_message,
            "You have not yet met what this technique requires: Need to know Thornweave",
        )

    def test_user_message_lists_multiple_failures(self) -> None:
        exc = TechniqueRequirementsNotMet(["Need to know Thornweave", "Need to hold Embercraft"])
        self.assertEqual(
            exc.user_message,
            "You have not yet met what this technique requires: "
            "Need to know Thornweave; Need to hold Embercraft",
        )

    def test_failed_attribute_preserved(self) -> None:
        failed = ["Need to know Thornweave"]
        exc = TechniqueRequirementsNotMet(failed)
        self.assertEqual(exc.failed, failed)


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
