"""Tests for battle exception default messages."""

from __future__ import annotations

from django.test import SimpleTestCase

from world.battles.exceptions import (
    CharacterDoesNotKnowTechniqueError,
    FortificationAlreadyBreachedError,
    FortificationOwnershipMismatchError,
    FortificationTargetRequiredError,
    InvalidMoveScopeError,
    MoveOrderRequiresTargetUnitError,
    PlaceScopeRequiredError,
    TechniqueNotBattleReadyError,
)


class BattleTechniqueExceptionTests(SimpleTestCase):
    def test_character_does_not_know_technique_default_message(self) -> None:
        exc = CharacterDoesNotKnowTechniqueError()
        self.assertEqual(exc.user_message, "You do not know that technique.")

    def test_technique_not_battle_ready_default_message(self) -> None:
        exc = TechniqueNotBattleReadyError()
        self.assertEqual(
            exc.user_message,
            "That technique cannot be used in battle (no action template).",
        )


class PlaceScopeRequiredErrorTests(SimpleTestCase):
    def test_default_message(self) -> None:
        exc = PlaceScopeRequiredError()
        self.assertEqual(
            exc.user_message,
            "That action can only be declared at a front (place scope).",
        )


class FortificationExceptionTests(SimpleTestCase):
    def test_fortification_target_required_error_message(self) -> None:
        exc = FortificationTargetRequiredError()
        self.assertIn("target fortification", exc.user_message)

    def test_fortification_ownership_mismatch_error_message(self) -> None:
        exc = FortificationOwnershipMismatchError()
        self.assertIn("BREACH", exc.user_message)

    def test_fortification_already_breached_error_message(self) -> None:
        exc = FortificationAlreadyBreachedError()
        self.assertIn("already been breached", exc.user_message)


class MoveExceptionTests(SimpleTestCase):
    def test_invalid_move_scope_error_default_message(self) -> None:
        exc = InvalidMoveScopeError()
        self.assertIn("MOVE", exc.user_message)

    def test_move_order_requires_target_unit_error_default_message(self) -> None:
        exc = MoveOrderRequiresTargetUnitError()
        self.assertIn("unit", exc.user_message.lower())
