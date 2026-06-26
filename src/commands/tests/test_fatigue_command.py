"""Tests for the telnet ``rest`` command (#1491)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.default_cmdsets import CharacterCmdSet
from commands.fatigue import CmdRest
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.constants import REST_AP_COST
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool


def _cmd(caller) -> CmdRest:
    cmd = CmdRest()
    cmd.caller = caller
    cmd.args = ""
    cmd.raw_string = "rest"
    cmd.cmdname = "rest"
    return cmd


class CmdRestTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        FatiguePool.flush_instance_cache()
        ActionPointPool.flush_instance_cache()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.room = create_object("typeclasses.rooms.Room", key="CmdRestHomeRoom", nohome=True)
        self.character.location = self.room
        self.character.home = self.room
        self.character.save()
        self.character.msg = MagicMock()

    def _create_ap_pool(self, current: int) -> ActionPointPool:
        return ActionPointPool.objects.create(
            character=self.character,
            current=current,
            maximum=200,
        )

    def test_rest_succeeds_and_messages(self) -> None:
        self._create_ap_pool(200)
        _cmd(self.character).func()
        self.character.msg.assert_called_once()
        sent = str(self.character.msg.call_args.args[0])
        self.assertIn("rest", sent.lower())
        pool = get_or_create_fatigue_pool(self.sheet)
        self.assertTrue(pool.well_rested)
        self.assertTrue(pool.rested_today)

    def test_rest_fails_and_messages_when_already_rested(self) -> None:
        self._create_ap_pool(200)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.rested_today = True
        pool.save()
        _cmd(self.character).func()
        sent = str(self.character.msg.call_args.args[0])
        self.assertIn("already rested", sent.lower())

    def test_rest_fails_and_messages_with_insufficient_ap(self) -> None:
        self._create_ap_pool(REST_AP_COST - 1)
        _cmd(self.character).func()
        sent = str(self.character.msg.call_args.args[0])
        self.assertIn("action points", sent.lower())


class CmdRestCmdsetRegistrationTests(TestCase):
    def test_rest_command_registered(self) -> None:
        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("rest", keys)
