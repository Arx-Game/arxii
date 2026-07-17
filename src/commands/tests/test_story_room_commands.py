"""Tests for the story-room telnet commands (#2450) — sceneroom/joinroom/leaveroom.

Mirrors ``test_setstage_command.py``'s harness shape: build real Character
objects with real accounts (staff or GM-tenured), call ``cmd.func()`` directly
with a stubbed ``caller.msg``, and assert on both the resulting DB state and
the messages sent back.
"""

from __future__ import annotations

from django.test import TestCase

from commands.story_rooms import CmdJoinRoom, CmdLeaveRoom, CmdSceneRoom
from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, StoryRoomGrantFactory
from world.gm.models import GMProfile
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _run(cmd_cls: type, args: str, caller: object) -> list[str]:
    cmd = cmd_cls()
    cmd.args = args
    cmd.caller = caller
    messages: list[str] = []
    caller.msg = lambda *a, **_k: messages.append(a[0] if a else "")
    cmd.func()
    return messages


def _make_room(key: str = "The Solar") -> object:
    from evennia import create_object

    return create_object("typeclasses.rooms.Room", key=key, nohome=True)


def _make_gm_character(key: str, room, level: str = GMLevel.STARTING) -> tuple[object, GMProfile]:
    """A Character with a live roster tenure + GMProfile at ``level``.

    Mirrors ``test_setstage_command.py``'s ``_make_gm_character`` helper.
    """
    char = CharacterFactory(db_key=key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    profile = GMProfileFactory(account=account, level=level)
    return char, profile


def _make_player_character(key: str, room) -> object:
    """A Character with a sheet but no GM standing."""
    char = CharacterFactory(db_key=key, home=room, location=room)
    CharacterSheetFactory(character=char)
    account = AccountFactory(username=f"account_{key}", is_staff=False)
    char.db_account = account
    return char


class SceneRoomSpinUpTests(TestCase):
    def test_spin_up_creates_active_gm_owned_instance(self) -> None:
        room = _make_room()
        gm, profile = _make_gm_character("spinner", room)

        msgs = _run(CmdSceneRoom, "Ambush Site = A dank trap.", gm)

        instance = InstancedRoom.objects.get(room__db_key="Ambush Site")
        assert instance.status == InstanceStatus.ACTIVE
        assert instance.gm_owner_id == profile.pk
        assert any("spun up" in m for m in msgs)

    def test_spin_up_requires_a_name(self) -> None:
        room = _make_room()
        gm, _profile = _make_gm_character("spinner_noname", room)

        msgs = _run(CmdSceneRoom, "= no name given", gm)

        assert not InstancedRoom.objects.filter(gm_owner__account=gm.db_account).exists()
        assert any("Usage: sceneroom" in m for m in msgs)

    def test_nonstaff_non_gm_caller_is_blocked(self) -> None:
        room = _make_room()
        caller = _make_player_character("noauthority", room)

        msgs = _run(CmdSceneRoom, "Should Not Exist = nope", caller)

        assert not InstancedRoom.objects.filter(room__db_key="Should Not Exist").exists()
        assert any("GM trust required." in m for m in msgs)


class SceneRoomCloseTests(TestCase):
    def test_close_returns_joiners(self) -> None:
        gm_room = _make_room("GM Room")
        gm, profile = _make_gm_character("closer", gm_room)
        origin_room = _make_room("Origin Room")
        player = _make_player_character("joiner", origin_room)

        _run(CmdSceneRoom, "Trap Room = A snare.", gm)
        instance = InstancedRoom.objects.get(room__db_key="Trap Room")
        StoryRoomGrantFactory(
            room=instance.room.room_profile, character=player.sheet_data, granted_by=profile
        )

        join_msgs = _run(CmdJoinRoom, str(instance.room_id), player)
        assert player.location == instance.room, join_msgs

        close_msgs = _run(CmdSceneRoom, f"close #{instance.room_id}", gm)

        player.refresh_from_db()
        assert player.location == origin_room
        assert not InstancedRoom.objects.filter(
            pk=instance.pk, status=InstanceStatus.ACTIVE
        ).exists()
        assert any("closed" in m for m in close_msgs)

    def test_close_requires_a_numeric_id(self) -> None:
        room = _make_room()
        gm, _profile = _make_gm_character("bad_closer", room)

        msgs = _run(CmdSceneRoom, "close not-a-number", gm)

        assert any("Usage: sceneroom" in m for m in msgs)


class JoinRoomTests(TestCase):
    def test_join_with_grant_moves_caller(self) -> None:
        gm_room = _make_room("GM Home")
        _gm, profile = _make_gm_character("granter", gm_room)
        origin_room = _make_room("Player Origin")
        player = _make_player_character("grantee", origin_room)
        story_room = RoomProfileFactory()
        StoryRoomGrantFactory(room=story_room, character=player.sheet_data, granted_by=profile)

        msgs = _run(CmdJoinRoom, str(story_room.objectdb_id), player)

        player.refresh_from_db()
        assert player.location == story_room.objectdb
        assert any("You join" in m for m in msgs)

    def test_join_without_grant_errors(self) -> None:
        origin_room = _make_room("Ungranted Origin")
        player = _make_player_character("ungranted", origin_room)
        story_room = RoomProfileFactory()

        msgs = _run(CmdJoinRoom, str(story_room.objectdb_id), player)

        player.refresh_from_db()
        assert player.location == origin_room
        assert any("no invitation" in m for m in msgs)

    def test_join_no_args_lists_grants(self) -> None:
        origin_room = _make_room("Lister Origin")
        player = _make_player_character("lister", origin_room)
        story_room = RoomProfileFactory()
        _gm, profile = _make_gm_character("lister_gm", _make_room("Lister GM Room"))
        StoryRoomGrantFactory(room=story_room, character=player.sheet_data, granted_by=profile)

        msgs = _run(CmdJoinRoom, "", player)

        joined = "\n".join(msgs)
        assert f"#{story_room.objectdb_id}" in joined
        assert story_room.objectdb.db_key in joined

    def test_join_no_args_no_grants(self) -> None:
        origin_room = _make_room("No Grants Origin")
        player = _make_player_character("nogrants", origin_room)

        msgs = _run(CmdJoinRoom, "", player)

        assert any("no story room grants" in m for m in msgs)


class LeaveRoomTests(TestCase):
    def test_leave_restores_origin(self) -> None:
        gm_room = _make_room("GM Home 2")
        _gm, profile = _make_gm_character("granter2", gm_room)
        origin_room = _make_room("Leaver Origin")
        player = _make_player_character("leaver", origin_room)
        story_room = RoomProfileFactory()
        StoryRoomGrantFactory(room=story_room, character=player.sheet_data, granted_by=profile)

        _run(CmdJoinRoom, str(story_room.objectdb_id), player)
        player.refresh_from_db()
        assert player.location == story_room.objectdb

        msgs = _run(CmdLeaveRoom, "", player)

        player.refresh_from_db()
        assert player.location == origin_room
        assert any("You leave." in m for m in msgs)

    def test_leave_outside_a_story_room_fails_cleanly(self) -> None:
        """No grant for the current (ordinary) room -- fails cleanly with the
        service's own message rather than raising."""
        origin_room = _make_room("Non-Story Origin")
        player = _make_player_character("notinastory", origin_room)

        msgs = _run(CmdLeaveRoom, "", player)

        player.refresh_from_db()
        assert player.location == origin_room
        assert any("no invitation" in m for m in msgs)
