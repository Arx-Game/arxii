"""Tests for CmdBattle (#1592).

Drives the ``battle declare strike <unit>`` subverb through the MagicMock
command harness (patterns doc §"Testing"): instantiate CmdBattle, set
``cmd.caller``, ``cmd.args``, call ``cmd.func()``, assert DB state and
telnet feedback.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.battle import CmdBattle
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.battles.constants import BattleActionKind
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.models import BattleActionDeclaration
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus


def _make_room(label: str = "CmdBattleRoom") -> object:
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _run(cmd: CmdBattle, caller: object, args: str) -> None:
    """Drive ``cmd.func()`` with the given *caller* and *args*."""
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"battle {args}".strip()
    caller.msg = MagicMock()
    cmd.func()


class CmdBattleDeclareTests(TestCase):
    """CmdBattle declare strike / declare support integration tests."""

    def setUp(self) -> None:
        self.room = _make_room()

        # Player character with a CharacterSheet.
        self.player_char = CharacterFactory(db_key="cmd_battle_player", location=self.room)
        self.player_sheet = CharacterSheetFactory(character=self.player_char)

        # Battle in the room.
        self.battle = BattleFactory(name="Cmd Test Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])

        # Two sides.
        self.attacker_side = BattleSideFactory(battle=self.battle, role="attacker")
        self.defender_side = BattleSideFactory(battle=self.battle, role="defender")

        # Unit on attacker side (strike target).
        self.unit = BattleUnitFactory(
            battle=self.battle,
            side=self.attacker_side,
            name="Iron Guard",
        )

        # Enlist player on defender side.
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=self.player_sheet,
        )

        # Open a DECLARING round.
        self.battle_round = BattleRoundFactory(
            battle=self.battle,
            round_number=1,
            status=RoundStatus.DECLARING,
        )

    def test_declare_strike_creates_declaration(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike Iron Guard")

        # Should have created a BattleActionDeclaration.
        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                target_unit=self.unit,
            ).exists()
        )

        # Caller should have received feedback.
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("declare", feedback.lower())

    def test_declare_support_creates_declaration(self) -> None:
        # Enlist an ally to support.
        ally_char = CharacterFactory(db_key="cmd_battle_ally", location=self.room)
        ally_sheet = CharacterSheetFactory(character=ally_char)
        ally_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=ally_sheet,
        )

        cmd = CmdBattle()
        _run(cmd, self.player_char, f"declare support {ally_char.db_key}")

        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.SUPPORT,
                target_ally=ally_participant,
            ).exists()
        )

    def test_declare_unknown_unit_sends_error(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike NonexistentUnit")

        # No declaration should have been created.
        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        # Should contain an error mentioning the missing unit.
        self.assertIn("NonexistentUnit", feedback)

    def test_bare_battle_shows_status(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "")
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Cmd Test Battle", feedback)

    def test_declare_without_kind_sends_usage(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare")
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Usage", feedback)

    def test_unknown_subverb_sends_error(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "flurgle")
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Usage", feedback)
