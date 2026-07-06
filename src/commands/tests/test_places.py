"""Tests for CmdPlaces — places / places join <name> / places leave (#1866)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.types import ActionResult
from commands.places import CmdPlaces
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PlaceFactory


class CmdPlacesTests(TestCase):
    def _caller(self, room):
        account = AccountFactory(username="cmdplaces_account")
        caller = CharacterFactory(db_key="CmdPlacesAlice", location=room)
        caller.db_account = account
        caller.save()
        CharacterSheetFactory(character=caller)
        return caller

    def _run(self, caller, args: str) -> list[str]:
        cmd = CmdPlaces()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"places {args}"
        messages: list[str] = []
        cmd.msg = lambda *a, **kw: messages.append(a[0] if a else "")  # noqa: ARG005
        cmd.func()
        return messages

    def test_join_resolves_place_by_name_in_current_room(self):
        room = ObjectDBFactory(db_key="CmdPlacesRoom", db_typeclass_path="typeclasses.rooms.Room")
        caller = self._caller(room)
        place = PlaceFactory(room=room, name="The Bar")
        with patch("commands.places.JoinPlaceAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Joined.")
            self._run(caller, "join The Bar")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["place"] == place

    def test_join_unknown_place_errors(self):
        room = ObjectDBFactory(db_key="CmdPlacesRoom2", db_typeclass_path="typeclasses.rooms.Room")
        caller = self._caller(room)
        messages = self._run(caller, "join Nowhere")
        assert any("No such place" in m for m in messages)

    def test_leave_dispatches_leave_place_action(self):
        room = ObjectDBFactory(db_key="CmdPlacesRoom3", db_typeclass_path="typeclasses.rooms.Room")
        caller = self._caller(room)
        place = PlaceFactory(room=room, name="The Bar")
        from world.scenes.factories import PersonaFactory
        from world.scenes.place_models import PlacePresence

        persona = PersonaFactory(character_sheet=caller.sheet_data)
        caller.sheet_data.active_persona = persona
        caller.sheet_data.save(update_fields=["active_persona"])
        PlacePresence.objects.create(place=place, persona=persona)
        with patch("commands.places.LeavePlaceAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Left.")
            self._run(caller, "leave")
        mocked.assert_called_once()
