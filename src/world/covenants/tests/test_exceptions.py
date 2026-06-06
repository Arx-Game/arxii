"""Tests for covenant typed exceptions."""

from django.test import SimpleTestCase

from world.covenants.exceptions import (
    CovenantEngagementPrerequisiteNotMetError,
    CovenantLevelTooLowError,
    CovenantNameConflictError,
    CovenantRiteError,
    CovenantRoleNeverHeldError,
    NoActiveBattleError,
    NotEnoughEngagedPresentError,
)


class CovenantRoleNeverHeldErrorTests(SimpleTestCase):
    def test_user_message(self) -> None:
        exc = CovenantRoleNeverHeldError()
        self.assertEqual(
            exc.user_message,
            "You must have held this role before you can weave a thread to it.",
        )
        self.assertIn(exc.user_message, CovenantRoleNeverHeldError.SAFE_MESSAGES)


class CovenantEngagementPrerequisiteNotMetErrorTests(SimpleTestCase):
    def test_user_message_in_safe_messages(self) -> None:
        exc = CovenantEngagementPrerequisiteNotMetError()
        self.assertEqual(
            exc.user_message,
            "No covenant members present to engage with.",
        )
        self.assertIn(exc.user_message, CovenantEngagementPrerequisiteNotMetError.SAFE_MESSAGES)


class CovenantNameConflictErrorTests(SimpleTestCase):
    def test_user_message_in_safe_messages(self) -> None:
        exc = CovenantNameConflictError()
        self.assertEqual(
            exc.user_message,
            "A covenant with that name already exists.",
        )
        self.assertIn(exc.user_message, CovenantNameConflictError.SAFE_MESSAGES)


class CovenantRiteExceptionTests(SimpleTestCase):
    def test_rite_exceptions_are_covenant_rite_errors(self) -> None:
        for exc_cls in (
            CovenantLevelTooLowError,
            NotEnoughEngagedPresentError,
            NoActiveBattleError,
        ):
            self.assertTrue(issubclass(exc_cls, CovenantRiteError))

    def test_user_messages_in_safe_messages(self) -> None:
        for exc_cls in (
            CovenantRiteError,
            CovenantLevelTooLowError,
            NotEnoughEngagedPresentError,
            NoActiveBattleError,
        ):
            exc = exc_cls()
            self.assertIn(exc.user_message, exc_cls.SAFE_MESSAGES)
