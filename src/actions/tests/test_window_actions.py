"""Tests for OpenWindowAction / CloseWindowAction (#2175)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.windows import CloseWindowAction, OpenWindowAction
from evennia_extensions.constants import ExitKind
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.models import ExitProfile, RoomProfile
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.services import transfer_ownership
from world.scenes.factories import PersonaFactory


class OpenWindowActionTests(TestCase):
    def _room_owner_and_window(self):
        room = ObjectDBFactory(db_key="WinRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(db_key="WinDest", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="win_account")
        actor = CharacterFactory(db_key="WinAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])

        room_profile = RoomProfile.objects.filter(objectdb=room).first()
        if room_profile is None:
            room_profile = RoomProfile.objects.create(objectdb=room)
        transfer_ownership(room_profile=room_profile, to_persona=persona)

        exit_obj = ObjectDBFactory(db_key="window", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()

        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.save()

        return actor, exit_obj

    def test_owner_can_open_window(self):
        actor, exit_obj = self._room_owner_and_window()
        result = OpenWindowAction().run(actor=actor, exit=exit_obj)
        assert result.success
        profile = ExitProfile.objects.get(objectdb=exit_obj)
        assert profile.is_open is True

    def test_owner_can_close_window(self):
        actor, exit_obj = self._room_owner_and_window()
        # Open it first
        OpenWindowAction().run(actor=actor, exit=exit_obj)
        result = CloseWindowAction().run(actor=actor, exit=exit_obj)
        assert result.success
        profile = ExitProfile.objects.get(objectdb=exit_obj)
        assert profile.is_open is False

    def test_non_owner_cannot_open_window(self):
        room = ObjectDBFactory(db_key="WinRoom2", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(db_key="WinDest2", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="win_account_2")
        actor = CharacterFactory(db_key="WinBob", location=room)
        actor.db_account = account
        actor.save()
        CharacterSheetFactory(character=actor)

        exit_obj = ObjectDBFactory(db_key="window2", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()

        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.save()

        result = OpenWindowAction().run(actor=actor, exit=exit_obj)
        assert not result.success

    def test_open_non_window_fails(self):
        actor, exit_obj = self._room_owner_and_window()
        # Change it back to a door
        profile = ExitProfile.objects.get(objectdb=exit_obj)
        profile.exit_kind = ExitKind.DOOR
        profile.save()

        result = OpenWindowAction().run(actor=actor, exit=exit_obj)
        assert not result.success
        assert "not a window" in result.message
