"""Tests for CmdPosition — position / position <name> / position/place (#2005, #3385)."""

from __future__ import annotations

from django.test import TestCase

from commands.positions import CmdPosition
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.areas.positioning.constants import PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class CmdPositionTests(TestCase):
    def _caller(self, room):
        # No CharacterSheet attached (mirrors world/areas/positioning/tests/test_take_position.py):
        # _can_move() treats a sheet-less ObjectDB as a non-character, always movable, without
        # requiring the MOVEMENT CapabilityType seed data.
        return CharacterFactory(db_key=f"CmdPositionAlice{room.pk}", location=room)

    def _run(self, caller, args: str) -> list[str]:
        cmd = CmdPosition()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"position {args}"
        messages: list[str] = []
        cmd.msg = lambda *a, **kw: messages.append(a[0] if a else "")  # noqa: ARG005
        cmd.func()
        return messages

    def test_bare_lists_positions_with_occupants(self):
        room = ObjectDBFactory(db_key="CmdPositionRoom", db_typeclass_path="typeclasses.rooms.Room")
        caller = self._caller(room)
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        place_in_position(caller, throne)

        messages = self._run(caller, "")

        assert any("throne" in m and "CmdPositionAlice" in m for m in messages)

    def test_bare_unstaged_room_reports_not_staged(self):
        room = ObjectDBFactory(
            db_key="CmdPositionRoomUnstaged", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = self._caller(room)

        messages = self._run(caller, "")

        assert any("no positions staged" in m for m in messages)

    def test_unplaced_actor_dispatches_take_position(self):
        room = ObjectDBFactory(
            db_key="CmdPositionRoomTake", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = self._caller(room)
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)

        self._run(caller, "throne")

        current = position_of(caller)
        assert current is not None
        assert current.pk == throne.pk

    def test_placed_actor_dispatches_move_to_adjacent_position(self):
        room = ObjectDBFactory(
            db_key="CmdPositionRoomMove", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = self._caller(room)
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        hearth = PositionFactory(room=room, name="hearth", kind=PositionKind.FEATURE)
        connect_positions(throne, hearth, is_passable=True)
        place_in_position(caller, throne)

        self._run(caller, "hearth")

        current = position_of(caller)
        assert current is not None
        assert current.pk == hearth.pk

    def test_unplaced_actor_targeting_ineligible_kind_surfaces_action_error(self):
        room = ObjectDBFactory(
            db_key="CmdPositionRoomIneligible", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = self._caller(room)
        PositionFactory(room=room, name="sky", kind=PositionKind.AERIAL)

        messages = self._run(caller, "sky")

        assert any("cannot enter" in m.lower() for m in messages)
        assert position_of(caller) is None

    def test_placed_actor_targeting_non_adjacent_position_surfaces_action_error(self):
        room = ObjectDBFactory(
            db_key="CmdPositionRoomBlocked", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = self._caller(room)
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        PositionFactory(room=room, name="hearth", kind=PositionKind.FEATURE)
        # No edge connecting throne and hearth.
        place_in_position(caller, throne)

        messages = self._run(caller, "hearth")

        assert any("no path" in m.lower() for m in messages)
        current = position_of(caller)
        assert current is not None
        assert current.pk == throne.pk

    def test_unknown_name_errors(self):
        room = ObjectDBFactory(
            db_key="CmdPositionRoomUnknown", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = self._caller(room)
        PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)

        messages = self._run(caller, "nowhere")

        assert any("No such position" in m for m in messages)

    def test_unique_prefix_resolves_position(self):
        room = ObjectDBFactory(
            db_key="CmdPositionRoomPrefix", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = self._caller(room)
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)

        self._run(caller, "thr")

        current = position_of(caller)
        assert current is not None
        assert current.pk == throne.pk


class CmdPositionPlaceTests(TestCase):
    """position/place <target>=<position name> (#3385).

    Thin coverage: parsing + dispatch only -- GMPlaceInPositionAction's own gate/
    mechanics are covered in ``actions/tests/test_gm_place_in_position_action.py``.
    """

    def _make_actor_with_account(self, db_key: str, room, account) -> object:
        char = CharacterFactory(db_key=db_key, location=room)
        CharacterSheetFactory(character=char)
        entry = RosterEntryFactory(character_sheet__character=char)
        RosterTenureFactory(roster_entry=entry, player_data__account=account, end_date=None)
        return char

    def _run(self, caller, args: str, switches: list[str]) -> list[str]:
        cmd = CmdPosition()
        cmd.caller = caller
        cmd.args = args
        cmd.switches = switches
        cmd.raw_string = f"position/{'/'.join(switches)} {args}"
        messages: list[str] = []
        cmd.msg = lambda *a, **kw: messages.append(a[0] if a else "")  # noqa: ARG005
        cmd.func()
        return messages

    def test_staff_places_co_located_target(self):
        room = ObjectDBFactory(
            db_key="CmdPositionPlaceRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        staff_account = AccountFactory(username="cmdplace_staff", is_staff=True)
        staff = self._make_actor_with_account("CmdPlaceStaff", room, staff_account)
        npc = CharacterFactory(db_key="CmdPlaceNPC", location=room)

        self._run(staff, "CmdPlaceNPC=throne", ["place"])

        current = position_of(npc)
        assert current is not None
        assert current.pk == throne.pk

    def test_scene_gm_places_co_located_target(self):
        room = ObjectDBFactory(
            db_key="CmdPositionPlaceGMRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        gm_account = AccountFactory(username="cmdplace_gm")
        gm = self._make_actor_with_account("CmdPlaceGM", room, gm_account)
        scene = SceneFactory(location=room)
        SceneParticipationFactory(scene=scene, account=gm_account, is_gm=True)
        npc = CharacterFactory(db_key="CmdPlaceGMNPC", location=room)

        self._run(gm, "CmdPlaceGMNPC=throne", ["place"])

        current = position_of(npc)
        assert current is not None
        assert current.pk == throne.pk

    def test_plain_player_denied(self):
        room = ObjectDBFactory(
            db_key="CmdPositionPlaceDeniedRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        player_account = AccountFactory(username="cmdplace_player")
        player = self._make_actor_with_account("CmdPlacePlayer", room, player_account)
        npc = CharacterFactory(db_key="CmdPlaceDeniedNPC", location=room)

        messages = self._run(player, "CmdPlaceDeniedNPC=throne", ["place"])

        assert any("only staff" in m.lower() or "gm" in m.lower() for m in messages)
        assert position_of(npc) is None

    def test_missing_equals_shows_usage(self):
        room = ObjectDBFactory(
            db_key="CmdPositionPlaceUsageRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        staff_account = AccountFactory(username="cmdplace_usage_staff", is_staff=True)
        staff = self._make_actor_with_account("CmdPlaceUsageStaff", room, staff_account)

        messages = self._run(staff, "notanassignment", ["place"])

        assert any("Usage: position/place" in m for m in messages)

    def test_non_co_located_target_not_found(self):
        room = ObjectDBFactory(
            db_key="CmdPositionPlaceElsewhereRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        other_room = ObjectDBFactory(
            db_key="CmdPositionPlaceOtherRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        staff_account = AccountFactory(username="cmdplace_elsewhere_staff", is_staff=True)
        staff = self._make_actor_with_account("CmdPlaceElsewhereStaff", room, staff_account)
        elsewhere_npc = CharacterFactory(db_key="CmdPlaceElsewhereNPC", location=other_room)

        # Co-located search only -- an object in another room can't be named.
        self._run(staff, "CmdPlaceElsewhereNPC=throne", ["place"])

        assert position_of(elsewhere_npc) is None
