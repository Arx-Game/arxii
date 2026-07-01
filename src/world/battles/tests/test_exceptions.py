"""Tests for battle exception default messages."""

from __future__ import annotations

from django.test import SimpleTestCase

from world.battles.exceptions import (
    CharacterDoesNotKnowTechniqueError,
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
