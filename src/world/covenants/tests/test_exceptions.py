"""Tests for covenant typed exceptions."""

from django.test import SimpleTestCase

from world.covenants.exceptions import CovenantRoleNeverHeldError


class CovenantRoleNeverHeldErrorTests(SimpleTestCase):
    def test_user_message(self) -> None:
        exc = CovenantRoleNeverHeldError()
        self.assertEqual(
            exc.user_message,
            "You must have held this role before you can weave a thread to it.",
        )
        self.assertIn(exc.user_message, CovenantRoleNeverHeldError.SAFE_MESSAGES)
