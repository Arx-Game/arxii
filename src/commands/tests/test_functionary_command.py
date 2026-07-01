"""Tests for the telnet ``functionary`` command (#1766)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.functionary import CmdFunctionary
from evennia_extensions.factories import RoomProfileFactory
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.npc_services.functionaries import functionaries_in_room
from world.npc_services.models import Functionary


def _cmd(args: str, *, staff: bool = True, location=None) -> CmdFunctionary:
    cmd = CmdFunctionary()
    cmd.caller = MagicMock()
    cmd.caller.check_permstring.return_value = staff
    cmd.caller.location = location
    cmd.args = args
    cmd.raw_string = f"functionary {args}".strip()
    cmd.cmdname = "functionary"
    return cmd


class CmdFunctionaryTests(TestCase):
    def test_list_shows_present(self) -> None:
        profile = RoomProfileFactory()
        FunctionaryFactory(role=NPCRoleFactory(name="Guild Clerk"), room=profile)
        cmd = _cmd("", location=profile.objectdb)
        cmd.func()
        self.assertIn("Guild Clerk", cmd.caller.msg.call_args.args[0])

    def test_list_empty(self) -> None:
        profile = RoomProfileFactory()
        cmd = _cmd("", location=profile.objectdb)
        cmd.func()
        self.assertIn("No functionaries", cmd.caller.msg.call_args.args[0])

    def test_place_creates_functionary_with_name(self) -> None:
        profile = RoomProfileFactory()
        role = NPCRoleFactory(name="Barkeep")
        cmd = _cmd(f"place {role.name}=Old Marta", staff=True, location=profile.objectdb)
        cmd.func()
        functionary = Functionary.objects.get(role=role, room=profile)
        self.assertEqual(functionary.name_override, "Old Marta")

    def test_place_requires_staff(self) -> None:
        profile = RoomProfileFactory()
        role = NPCRoleFactory(name="Barkeep")
        cmd = _cmd(f"place {role.name}", staff=False, location=profile.objectdb)
        cmd.func()
        self.assertFalse(Functionary.objects.filter(role=role).exists())
        self.assertIn("staff", cmd.caller.msg.call_args.args[0].lower())

    def test_remove(self) -> None:
        profile = RoomProfileFactory()
        role = NPCRoleFactory(name="Town Guard")
        FunctionaryFactory(role=role, room=profile)
        cmd = _cmd(f"remove {role.name}", staff=True, location=profile.objectdb)
        cmd.func()
        self.assertFalse(functionaries_in_room(profile).exists())

    def test_no_room_reports_cleanly(self) -> None:
        cmd = _cmd("", location=None)
        cmd.func()
        self.assertIn("not in a room", cmd.caller.msg.call_args.args[0])
