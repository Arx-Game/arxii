"""Tests for Place, PlacePresence, and InteractionReceiver models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.scenes.constants import PlaceStatus
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    PersonaFactory,
    PlaceFactory,
    PlacePresenceFactory,
)


class TestPlace(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_create_place(self) -> None:
        place = PlaceFactory(room=self.room, name="The Bar")
        assert place.name == "The Bar"
        assert place.room == self.room
        assert place.status == PlaceStatus.ACTIVE

    def test_unique_name_per_room(self) -> None:
        PlaceFactory(room=self.room, name="Corner Booth")
        with self.assertRaises(IntegrityError):
            PlaceFactory(room=self.room, name="Corner Booth")

    def test_duplicate_names_allowed_across_rooms(self) -> None:
        other_room = ObjectDBFactory(
            db_key="Inn",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        PlaceFactory(room=self.room, name="Hearth")
        place2 = PlaceFactory(room=other_room, name="Hearth")
        assert place2.pk is not None

    def test_str(self) -> None:
        place = PlaceFactory(name="Corner Booth")
        assert "Corner Booth" in str(place)


class TestPlacePresence(TestCase):
    def test_create_presence(self) -> None:
        place = PlaceFactory()
        persona = PersonaFactory()
        presence = PlacePresenceFactory(place=place, persona=persona)
        assert presence.place == place
        assert presence.persona == persona
        assert presence.arrived_at is not None

    def test_unique_persona_per_place(self) -> None:
        place = PlaceFactory()
        persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)
        with self.assertRaises(IntegrityError):
            PlacePresenceFactory(place=place, persona=persona)

    def test_str(self) -> None:
        presence = PlacePresenceFactory()
        assert "at" in str(presence)


class TestInteractionReceiver(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()

    def test_create_receiver(self) -> None:
        interaction = InteractionFactory()
        receiver = InteractionReceiverFactory(
            interaction=interaction,
            persona=self.persona,
        )
        assert receiver.interaction == interaction
        assert receiver.persona == self.persona
        assert receiver.timestamp == interaction.timestamp

    def test_unique_receiver_per_interaction(self) -> None:
        interaction = InteractionFactory()
        InteractionReceiverFactory(
            interaction=interaction,
            persona=self.persona,
        )
        with self.assertRaises(IntegrityError):
            InteractionReceiverFactory(
                interaction=interaction,
                persona=self.persona,
            )

    def test_clean_validates_timestamp(self) -> None:
        interaction = InteractionFactory()
        receiver = InteractionReceiverFactory.build(
            interaction=interaction,
            persona=self.persona,
            timestamp=interaction.timestamp,
        )
        # Should not raise -- timestamps match
        receiver.clean()

    def test_str(self) -> None:
        receiver = InteractionReceiverFactory()
        assert "received interaction" in str(receiver)

    def test_interaction_cached_receivers(self) -> None:
        interaction = InteractionFactory()
        InteractionReceiverFactory(interaction=interaction, persona=self.persona)
        receivers = interaction.cached_receivers
        assert len(receivers) == 1
        assert receivers[0].persona == self.persona
