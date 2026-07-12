"""Tests for the #2177 defense install/upgrade/fund Actions."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.room_features import StartDefenseInstallationAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.services import transfer_ownership
from world.room_features.constants import DefenseKind
from world.scenes.factories import PersonaFactory


class StartDefenseInstallationActionTests(TestCase):
    def _owner_actor_and_room(self):
        room = ObjectDBFactory(db_key="SDIRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="sdi_account")
        actor = CharacterFactory(db_key="SDIAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        room_profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        transfer_ownership(room_profile=room_profile, to_persona=persona)
        return actor, room, room_profile

    def test_install_bars_on_exit(self):
        actor, room, _room_profile = self._owner_actor_and_room()
        dest = ObjectDBFactory(db_key="SDIDest", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="east", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()

        result = StartDefenseInstallationAction().run(
            actor=actor,
            defense_kind=DefenseKind.EXIT_BARS,
            target_level=1,
            exit=exit_obj,
        )
        assert result.success
        from world.projects.models import Project

        assert Project.objects.filter(pk=result.data["project_id"]).exists()

    def test_install_ward_requires_resonance(self):
        actor, _room, _room_profile = self._owner_actor_and_room()
        result = StartDefenseInstallationAction().run(
            actor=actor, defense_kind=DefenseKind.ROOM_WARD, target_level=1
        )
        assert not result.success

    def test_install_ward_with_resonance(self):
        from world.magic.factories import ResonanceFactory

        actor, _room, _room_profile = self._owner_actor_and_room()
        resonance = ResonanceFactory()
        result = StartDefenseInstallationAction().run(
            actor=actor,
            defense_kind=DefenseKind.ROOM_WARD,
            target_level=1,
            resonance=resonance,
        )
        assert result.success

    def test_install_alarm(self):
        actor, _room, _room_profile = self._owner_actor_and_room()
        result = StartDefenseInstallationAction().run(
            actor=actor, defense_kind=DefenseKind.ROOM_ALARM, target_level=1
        )
        assert result.success

    def test_non_owner_cannot_install(self):
        room = ObjectDBFactory(db_key="SDIRoom2", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="sdi_account2")
        actor = CharacterFactory(db_key="SDIBob", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        result = StartDefenseInstallationAction().run(
            actor=actor, defense_kind=DefenseKind.ROOM_ALARM, target_level=1
        )
        assert not result.success

    def test_level_exceeding_max_rejected(self):
        actor, _room, _room_profile = self._owner_actor_and_room()
        result = StartDefenseInstallationAction().run(
            actor=actor, defense_kind=DefenseKind.ROOM_ALARM, target_level=99
        )
        assert not result.success

    def test_install_alarm_not_an_upgrade_rejected(self):
        from world.room_features.models import RoomAlarmDetails

        actor, _room, room_profile = self._owner_actor_and_room()
        RoomAlarmDetails.objects.create(room_profile=room_profile, level=1)

        result = StartDefenseInstallationAction().run(
            actor=actor, defense_kind=DefenseKind.ROOM_ALARM, target_level=1
        )
        assert result.success is False

    def test_install_bars_not_an_upgrade_rejected(self):
        from evennia_extensions.models import ExitProfile
        from world.room_features.models import ExitBarsDetails

        actor, room, _room_profile = self._owner_actor_and_room()
        dest = ObjectDBFactory(db_key="SDIDest2", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="west", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        ExitBarsDetails.objects.create(exit_profile=exit_profile, level=1)

        result = StartDefenseInstallationAction().run(
            actor=actor,
            defense_kind=DefenseKind.EXIT_BARS,
            target_level=1,
            exit=exit_obj,
        )
        assert result.success is False

    def test_install_bars_via_exit_id_kwarg(self):
        actor, room, _room_profile = self._owner_actor_and_room()
        dest = ObjectDBFactory(db_key="SDIDest3", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="up", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()

        result = StartDefenseInstallationAction().run(
            actor=actor,
            defense_kind=DefenseKind.EXIT_BARS,
            target_level=1,
            exit_id=exit_obj.pk,
        )
        assert result.success
        from world.projects.models import Project

        assert Project.objects.filter(pk=result.data["project_id"]).exists()
