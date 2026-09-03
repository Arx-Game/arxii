"""Telnet ``story clock [n]`` dispatches AdvanceClockAction (#3567)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.story import CmdStory
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.clock_services import open_clock_for_beat, start_scene_clock
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.stories.factories import BeatFactory


def _make_room(label: str) -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _run_story_cmd(caller: object, args: str) -> list[str]:
    caller.msg = MagicMock()
    cmd = CmdStory()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"story {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class StoryClockCommandTests(TestCase):
    """A scene GM ticks the running beat's clock through the telnet subverb."""

    def setUp(self) -> None:
        self.room = _make_room("ClockRoom")
        self.gm_account = AccountFactory(username="clockgm")
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)
        self.gm_actor = CharacterFactory(db_key="clock_gm_actor", location=self.room)
        sheet = CharacterSheetFactory(character=self.gm_actor)
        RosterTenureFactory(
            roster_entry__character_sheet=sheet,
            player_data__account=self.gm_account,
            end_date=None,
        )
        self.beat = BeatFactory(clock_size=2)
        self.scene = SceneFactory(location=self.room, is_active=True, running_beat=self.beat)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        start_scene_clock(self.scene, self.beat)

    def test_clock_advances_by_one_by_default(self) -> None:
        messages = _run_story_cmd(self.gm_actor, "clock")
        clock = open_clock_for_beat(self.beat)
        self.assertEqual(clock.filled, 1)
        self.assertTrue(any("1/2" in m for m in messages), messages)

    def test_bad_token_raises_usage_without_dispatching(self) -> None:
        messages = _run_story_cmd(self.gm_actor, "clock x")
        clock = open_clock_for_beat(self.beat)
        self.assertEqual(clock.filled, 0)
        self.assertTrue(any("Usage" in m for m in messages), messages)
