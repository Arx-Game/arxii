"""Tests for the reachability predicate (#3787 decision 3).

Each case below breaks the invariant it proves: the "not reachable" tests
construct a persona genuinely outside the venue and assert the refusal,
rather than only checking the happy path still passes.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory, PlaceFactory, PlacePresenceFactory, SceneFactory
from world.scenes.reachability import UnreachableError, persona_can_receive


def _persona_at(room) -> object:
    """Build a Persona whose character is physically located in ``room``."""
    character = CharacterFactory(location=room)
    sheet = CharacterSheetFactory(character=character)
    return PersonaFactory(character_sheet=sheet)


class TestPersonaCanReceiveRoomHeard(TestCase):
    """Room-heard shape: no place, no receivers, not a whisper."""

    def test_persona_present_in_room_is_reachable(self) -> None:
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(room)

        assert persona_can_receive(
            persona, scene=scene, place=None, receivers=None, mode=InteractionMode.POSE
        )

    def test_persona_elsewhere_is_not_reachable(self) -> None:
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        other_room = ObjectDBFactory(db_key="Cellar", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(other_room)

        assert not persona_can_receive(
            persona, scene=scene, place=None, receivers=None, mode=InteractionMode.POSE
        )

    def test_no_scene_is_not_reachable(self) -> None:
        # No room to test presence against - reachability cannot be confirmed,
        # so the predicate refuses rather than guessing.
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        persona = _persona_at(room)

        assert not persona_can_receive(
            persona, scene=None, place=None, receivers=None, mode=InteractionMode.POSE
        )


class TestPersonaCanReceivePlaceScoped(TestCase):
    """Place-scoped shape: reachability is PlacePresence, never the room at large."""

    def test_persona_at_different_place_is_not_reachable(self) -> None:
        room = RoomProfileFactory()
        place = PlaceFactory(room=room, name="the bar")
        other_place = PlaceFactory(room=room, name="the hearth")
        persona = PersonaFactory()
        PlacePresenceFactory(place=other_place, persona=persona)

        assert not persona_can_receive(
            persona, scene=None, place=place, receivers=None, mode=InteractionMode.POSE
        )

    def test_persona_at_same_place_is_reachable(self) -> None:
        room = RoomProfileFactory()
        place = PlaceFactory(room=room, name="the bar")
        persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)

        assert persona_can_receive(
            persona, scene=None, place=place, receivers=None, mode=InteractionMode.POSE
        )

    def test_persona_at_place_but_not_an_explicit_receiver_is_not_reachable(self) -> None:
        # A Place row may ALSO narrow to a specific listener (a private aside at
        # the table) - being physically present is necessary but not sufficient.
        room = RoomProfileFactory()
        place = PlaceFactory(room=room, name="the bar")
        persona = PersonaFactory()
        other_persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)

        assert not persona_can_receive(
            persona,
            scene=None,
            place=place,
            receivers=[other_persona.pk],
            mode=InteractionMode.POSE,
        )


class TestPersonaCanReceiveWhisper(TestCase):
    """Whisper shape: reachable only for the named party, regardless of location."""

    def test_persona_outside_whisper_party_is_not_reachable(self) -> None:
        party_persona = PersonaFactory()
        outsider = PersonaFactory()

        assert not persona_can_receive(
            outsider,
            scene=None,
            place=None,
            receivers=[party_persona.pk],
            mode=InteractionMode.WHISPER,
        )

    def test_persona_in_whisper_party_is_reachable(self) -> None:
        party_persona = PersonaFactory()

        assert persona_can_receive(
            party_persona,
            scene=None,
            place=None,
            receivers=[party_persona.pk],
            mode=InteractionMode.WHISPER,
        )

    def test_whisper_with_no_receivers_is_not_reachable(self) -> None:
        persona = PersonaFactory()

        assert not persona_can_receive(
            persona, scene=None, place=None, receivers=None, mode=InteractionMode.WHISPER
        )


class TestPersonaCanReceiveDirectedReceivers(TestCase):
    """Explicit receivers without a Place: a targeted mutter in the open room."""

    def test_persona_not_in_receiver_list_is_not_reachable(self) -> None:
        receiver = PersonaFactory()
        outsider = PersonaFactory()

        assert not persona_can_receive(
            outsider, scene=None, place=None, receivers=[receiver.pk], mode=InteractionMode.POSE
        )

    def test_persona_in_receiver_list_is_reachable(self) -> None:
        receiver = PersonaFactory()

        assert persona_can_receive(
            receiver, scene=None, place=None, receivers=[receiver.pk], mode=InteractionMode.POSE
        )

    def test_receivers_accepts_persona_instances_not_just_ids(self) -> None:
        receiver = PersonaFactory()

        assert persona_can_receive(
            receiver,
            scene=None,
            place=None,
            receivers=[receiver],
            mode=InteractionMode.POSE,
        )


class TestUnreachableError(TestCase):
    def test_carries_personas_and_venue_hint(self) -> None:
        persona = PersonaFactory()

        error = UnreachableError([persona], "Leave the bar to answer this.")

        assert error.personas == [persona]
        assert error.venue_hint == "Leave the bar to answer this."
        assert str(error) == "Leave the bar to answer this."
