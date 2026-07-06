"""Tests for JoinPlaceAction / LeavePlaceAction (#1866)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.places import JoinPlaceAction, LeavePlaceAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory, PlaceFactory
from world.scenes.place_models import PlacePresence


class JoinPlaceActionTests(TestCase):
    def test_join_place_creates_presence_for_active_persona(self):
        room = ObjectDBFactory(db_key="JoinPlaceRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="join_place_account")
        actor = CharacterFactory(db_key="JoinPlaceAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        place = PlaceFactory(room=room, name="The Bar")

        result = JoinPlaceAction().run(actor=actor, place=place)
        assert result.success
        assert PlacePresence.objects.filter(place=place, persona=persona).exists()

    def test_join_place_without_place_kwarg_fails(self):
        room = ObjectDBFactory(
            db_key="JoinPlaceNoTargetRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="join_place_no_target_account")
        actor = CharacterFactory(db_key="JoinPlaceNoTargetAlice", location=room)
        actor.db_account = account
        actor.save()
        CharacterSheetFactory(character=actor)

        result = JoinPlaceAction().run(actor=actor)
        assert not result.success


class LeavePlaceActionTests(TestCase):
    def test_leave_place_removes_presence(self):
        room = ObjectDBFactory(db_key="LeavePlaceRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="leave_place_account")
        actor = CharacterFactory(db_key="LeavePlaceAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        place = PlaceFactory(room=room, name="The Bar")
        PlacePresence.objects.create(place=place, persona=persona)

        result = LeavePlaceAction().run(actor=actor, place=place)
        assert result.success
        assert not PlacePresence.objects.filter(place=place, persona=persona).exists()

    def test_leave_place_when_not_present_fails(self):
        room = ObjectDBFactory(
            db_key="LeavePlaceAbsentRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="leave_place_absent_account")
        actor = CharacterFactory(db_key="LeavePlaceAbsentAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        PersonaFactory(character_sheet=sheet)
        place = PlaceFactory(room=room, name="The Hearth")

        result = LeavePlaceAction().run(actor=actor, place=place)
        assert not result.success
