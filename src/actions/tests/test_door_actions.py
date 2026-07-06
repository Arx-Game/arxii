"""Tests for door LockAction/UnlockAction and the can_traverse gate (#1866)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.doors import LockAction, UnlockAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.services import transfer_ownership
from world.scenes.factories import PersonaFactory


class LockActionTests(TestCase):
    def _room_owner_and_exit(self):
        room = ObjectDBFactory(db_key="DoorLockRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="DoorLockDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="door_lock_account")
        actor = CharacterFactory(db_key="DoorLockAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        from evennia_extensions.models import RoomProfile

        room_profile = RoomProfile.objects.filter(objectdb=room).first()
        if room_profile is None:
            room_profile = RoomProfile.objects.create(objectdb=room)
        transfer_ownership(room_profile=room_profile, to_persona=persona)
        exit_obj = ObjectDBFactory(db_key="north", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()
        return actor, exit_obj

    def test_owner_can_lock_exit(self):
        actor, exit_obj = self._room_owner_and_exit()
        result = LockAction().run(actor=actor, exit=exit_obj)
        assert result.success
        assert exit_obj.db.locked is True

    def test_non_owner_cannot_lock_exit(self):
        room = ObjectDBFactory(db_key="DoorLockRoom2", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="DoorLockDest2", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="door_lock_account_2")
        actor = CharacterFactory(db_key="DoorLockBob", location=room)
        actor.db_account = account
        actor.save()
        CharacterSheetFactory(character=actor)
        exit_obj = ObjectDBFactory(db_key="south", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()

        result = LockAction().run(actor=actor, exit=exit_obj)
        assert not result.success


class UnlockActionTests(TestCase):
    def test_owner_can_unlock_exit(self):
        actor, exit_obj = LockActionTests()._room_owner_and_exit()
        exit_obj.db.locked = True
        result = UnlockAction().run(actor=actor, exit=exit_obj)
        assert result.success
        assert exit_obj.db.locked is False
