"""Telnet battle command tests (#1899) — CmdBattle._status() paused display."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.battle import CmdBattle
from evennia_extensions.factories import CharacterFactory
from world.battles.constants import BattleParticipantStatus
from world.battles.factories import BattleFactory, BattleParticipantFactory, BattleSideFactory
from world.character_sheets.factories import CharacterSheetFactory


class BattleStatusPausedLineTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="BattleStatusTester")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.character.msg = MagicMock()
        self.battle = BattleFactory()
        side = BattleSideFactory(battle=self.battle)
        BattleParticipantFactory(
            battle=self.battle,
            side=side,
            character_sheet=self.sheet,
            status=BattleParticipantStatus.ACTIVE,
        )

    def _run_status(self) -> str:
        cmd = CmdBattle()
        cmd.caller = self.character
        cmd.args = ""
        cmd.switches = []
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)

    def test_status_shows_paused_line_when_battle_is_paused(self) -> None:
        self.battle.is_paused = True
        self.battle.save(update_fields=["is_paused"])

        out = self._run_status()

        assert "PAUSED" in out

    def test_status_omits_paused_line_when_not_paused(self) -> None:
        out = self._run_status()

        assert "PAUSED" not in out
