"""Tests for CmdPosition — position / position <name> (#2005)."""

from __future__ import annotations

from django.test import TestCase

from commands.positions import CmdPosition
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.areas.positioning.constants import PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of


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
