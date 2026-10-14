"""A typed ``/switch`` reaches the command that reads it.

``ArxCommand`` subclasses Evennia's base ``Command``, whose ``parse()`` does nothing;
only Evennia's ``MuxCommand`` splits ``market/finish 12`` into the switch ``finish``
and the arguments ``12``. So every ``ArxCommand`` that read ``self.switches`` raised
``AttributeError`` when typed, and the ones that read it defensively took their
switch-less branch with ``/set`` still sitting in their arguments: ``home/set``
recalled the character home instead of setting it. Every command test set
``switches`` by hand, so none of them ever ran the parser. These tests type the
line through Evennia's command handler instead.
"""

from __future__ import annotations

import inspect
from unittest.mock import Mock, patch

from django.test import TestCase
from evennia.commands.cmdset import CmdSet

from commands.command import ArxCommand, DispatchCommand
from commands.default_cmdsets import (
    AccountCmdSet,
    CharacterCmdSet,
    SessionCmdSet,
    UnloggedinCmdSet,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from evennia_extensions.models import PlayerData
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.locations.services import assign_room_tenant
from world.scenes.models import Mute


class _SwitchProbe(ArxCommand):
    """Echoes what the parser handed it."""

    key = "switchprobe"
    locks = "cmd:all()"

    def func(self) -> None:
        self.caller.msg(f"switches={list(self.switches)} args={self.args!r}")


class _SwitchProbeCmdSet(CmdSet):
    key = "switch_probe"

    def at_cmdset_creation(self) -> None:
        self.add(_SwitchProbe())


def _played(name: str, room):
    """A character in ``room`` with a sheet and an account behind it."""
    character = CharacterFactory(db_key=name, location=room)
    # Evennia's command handler reads the account's nicks before it runs anything.
    character.db_account = AccountFactory(username=f"switch_{name.lower()}")
    character.save()
    CharacterSheetFactory(character=character)
    return character


def _typed(character, line: str) -> list[object]:
    """Type ``line`` as ``character`` through Evennia's command handler; return the replies."""
    with patch.object(character, "msg") as msg:
        character.execute_cmd(line)
    return [call.args[0] if call.args else call.kwargs.get("text") for call in msg.call_args_list]


class TypedSwitchTests(TestCase):
    def setUp(self) -> None:
        self.area = AreaFactory(level=AreaLevel.BUILDING)
        self.room = RoomProfileFactory(area=self.area).objectdb
        self.speaker = _played("Rowan", self.room)

    def test_a_switch_is_split_off_the_arguments(self) -> None:
        self.speaker.cmdset.add(_SwitchProbeCmdSet)

        replies = _typed(self.speaker, "switchprobe/Finish/two Heron Plate = gilt")

        assert replies == ["switches=['finish', 'two'] args=' Heron Plate = gilt'"]

    def test_a_switch_alone_leaves_no_arguments(self) -> None:
        self.speaker.cmdset.add(_SwitchProbeCmdSet)

        assert _typed(self.speaker, "switchprobe/list") == ["switches=['list'] args=''"]

    def test_a_line_without_a_switch_keeps_its_arguments(self) -> None:
        self.speaker.cmdset.add(_SwitchProbeCmdSet)

        replies = _typed(self.speaker, "switchprobe a/b and c")

        assert replies == ["switches=[] args=' a/b and c'"]

    def test_home_set_sets_the_home_instead_of_recalling(self) -> None:
        """The defensive read took ``home/set`` for a bare ``home`` and walked them away."""
        old_home = RoomProfileFactory(area=self.area).objectdb
        self.speaker.home = old_home
        self.speaker.save()
        owner = CharacterSheetFactory(character=CharacterFactory()).primary_persona
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.area,
            holder_type=HolderType.PERSONA,
            holder_persona=owner,
        )
        assign_room_tenant(
            persona=owner,
            room=self.room,
            tenant_persona=self.speaker.sheet_data.primary_persona,
        )

        _typed(self.speaker, "home/set")

        assert self.speaker.location == self.room
        assert self.speaker.home == self.room

    def test_mute_persona_mutes_only_that_face(self) -> None:
        """``/persona`` reached the search as part of the name, so nobody was found."""
        _played("Linden", self.room)

        replies = _typed(self.speaker, "+mute/persona Linden")

        owner = PlayerData.objects.get(account=self.speaker.account)
        mute = Mute.objects.get(owner=owner)
        assert mute.account_level is False
        assert replies == ["Muted Linden (IC/OOC, this character only)."]


def _reads_switches(command_class: type) -> bool:
    """True when our own code in the command's class chain reads ``switches``."""
    for klass in command_class.__mro__:
        if klass.__module__.split(".")[0] in {"evennia", "builtins"}:
            continue
        # The bases define the parse; what matters is a command that relies on it.
        if klass in (ArxCommand, DispatchCommand):
            continue
        if "switches" in inspect.getsource(klass):
            return True
    return False


class EveryCommandThatReadsSwitchesParsesThemTests(TestCase):
    """The guard for the class of bug: a command reading switches its parser never set."""

    def test_the_switch_never_stays_in_the_arguments(self) -> None:
        cmdsets = (CharacterCmdSet(), AccountCmdSet(), SessionCmdSet(), UnloggedinCmdSet())
        commands = {type(cmd): cmd for cmdset in cmdsets for cmd in cmdset.commands}
        checked, unparsed = [], []
        for command_class, command in commands.items():
            if not _reads_switches(command_class):
                continue
            cmd = command_class()
            # A plain Mock, so a parser that warns about an unknown switch can say so.
            cmd.caller = Mock()
            cmd.session = None
            cmd.cmdstring = command.key
            cmd.raw_string = f"{command.key}/probe the rest"
            cmd.args = "/probe the rest"
            cmd.parse()
            checked.append(command_class.__name__)
            if "/probe" in cmd.args:
                unparsed.append(command_class.__name__)

        assert "CmdMarket" in checked
        assert "CmdSheet" in checked
        assert unparsed == []
