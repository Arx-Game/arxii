"""Tests for place services."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import PersonaFactory, PlaceFactory, PlacePresenceFactory
from world.scenes.place_models import PlacePresence
from world.scenes.place_services import ensure_scene_for_location, join_place, leave_place


class TestEnsureSceneForLocation(TestCase):
    def test_creates_scene_when_none_exists(self) -> None:
        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        scene = ensure_scene_for_location(room)
        assert scene.pk is not None
        assert scene.is_active is True
        assert scene.location == room
        assert scene.privacy_mode == ScenePrivacyMode.PUBLIC

    def test_returns_existing_active_scene(self) -> None:
        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        scene1 = ensure_scene_for_location(room)
        scene2 = ensure_scene_for_location(room)
        assert scene1.pk == scene2.pk

    def test_custom_name(self) -> None:
        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        scene = ensure_scene_for_location(room, name="A Dramatic Evening")
        assert scene.name == "A Dramatic Evening"


class TestJoinPlace(TestCase):
    def test_join_creates_presence(self) -> None:
        place = PlaceFactory()
        persona = PersonaFactory()
        presence = join_place(place=place, persona=persona)
        assert presence.pk is not None
        assert presence.place == place
        assert presence.persona == persona

    def test_join_idempotent(self) -> None:
        place = PlaceFactory()
        persona = PersonaFactory()
        presence1 = join_place(place=place, persona=persona)
        presence2 = join_place(place=place, persona=persona)
        assert presence1.pk == presence2.pk

    def test_join_removes_from_other_places_in_room(self) -> None:
        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        place1 = PlaceFactory(room=room, name="Bar")
        place2 = PlaceFactory(room=room, name="Corner")
        persona = PersonaFactory()

        join_place(place=place1, persona=persona)
        assert PlacePresence.objects.filter(place=place1, persona=persona).exists()

        join_place(place=place2, persona=persona)
        assert not PlacePresence.objects.filter(place=place1, persona=persona).exists()
        assert PlacePresence.objects.filter(place=place2, persona=persona).exists()


class TestLeavePlace(TestCase):
    def test_leave_removes_presence(self) -> None:
        place = PlaceFactory()
        persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)

        result = leave_place(place=place, persona=persona)
        assert result is True
        assert not PlacePresence.objects.filter(place=place, persona=persona).exists()

    def test_leave_when_not_present(self) -> None:
        place = PlaceFactory()
        persona = PersonaFactory()

        result = leave_place(place=place, persona=persona)
        assert result is False
