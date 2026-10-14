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
import re
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
    takes_switches = True
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

    def test_a_command_without_switches_keeps_the_slash(self) -> None:
        """Dropping an unread switch would run the rest: ``+unmute/x Linden`` would unmute."""
        _played("Linden", self.room)

        replies = _typed(self.speaker, "+unmute/x Linden")

        # Evennia's search says it, then the command's error repeats it.
        assert set(replies) == {"Could not find '/x Linden'."}

    def test_an_unmatched_line_keeps_its_slash(self) -> None:
        """``CMD_NOMATCH`` is handed the whole typed line as its arguments."""
        replies = _typed(self.speaker, "/zzqxv now")

        assert replies == [
            ("Command '/zzqxv now' is not available. Type \"help\" for help.", {"type": "error"})
        ]

    def test_an_unknown_sheet_section_is_refused(self) -> None:
        """A mistyped section is refused, never answered with the overview instead."""
        replies = _typed(self.speaker.account, "sheet/typo")

        assert len(replies) == 1
        assert replies[0].startswith("No sheet section 'typo'.")


_READS_SWITCHES = re.compile(r"\.switches\b")


def _own_sources(command_class: type) -> list[str]:
    """Our code behind ``command_class``: its classes and the module helpers they call.

    Evennia's classes are left out, and so are the two bases, which define the parse
    rather than rely on it. A module helper counts when the class calls it by name:
    ``+mute`` reads its switches in ``_account_scope_from_switches(self)``.
    """
    sources = []
    for klass in command_class.__mro__:
        if klass.__module__.split(".")[0] in {"evennia", "builtins"}:
            continue
        if klass in (ArxCommand, DispatchCommand):
            continue
        source = inspect.getsource(klass)
        sources.append(source)
        module = inspect.getmodule(klass)
        for name, value in vars(module).items():
            if (
                inspect.isfunction(value)
                and value.__module__ == module.__name__
                and re.search(rf"\b{name}\(", source)
            ):
                sources.append(inspect.getsource(value))
    return sources


def _reads_switches(command_class: type) -> bool:
    """True when our own code behind the command reads ``.switches``."""
    return any(_READS_SWITCHES.search(source) for source in _own_sources(command_class))


def _game_commands() -> dict[type, object]:
    """Every command class in the game's cmdsets, with one instance of each."""
    cmdsets = (CharacterCmdSet(), AccountCmdSet(), SessionCmdSet(), UnloggedinCmdSet())
    return {type(cmd): cmd for cmdset in cmdsets for cmd in cmdset.commands}


class EveryCommandThatReadsSwitchesParsesThemTests(TestCase):
    """The guard for the class of bug: a command reading switches its parser never set."""

    def test_an_arx_command_takes_switches_exactly_when_it_reads_them(self) -> None:
        """Both ways: a reader that never opts in crashes or takes the wrong branch, and a
        command that opts in without reading them drops what was typed (``retire/x``
        would retire)."""
        mismatched = [
            command_class.__name__
            for command_class in _game_commands()
            if issubclass(command_class, ArxCommand)
            and command_class.takes_switches != _reads_switches(command_class)
        ]

        assert mismatched == []

    def test_every_reader_has_the_switch_split_off_its_arguments(self) -> None:
        checked, unparsed = [], []
        for command_class, command in _game_commands().items():
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

        assert {"CmdMarket", "CmdEmit", "CmdMute", "CmdSheet"} <= set(checked)
        assert unparsed == []
