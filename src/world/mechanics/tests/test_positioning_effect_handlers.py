"""Tests for CREATE_POSITION and MOVE_TO_POSITION effect handlers.

Built using setUp (not setUpTestData) — Evennia ObjectDB instances (DbHolder)
are not deepcopyable and would break setUpTestData.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    edge_between,
    place_in_position,
    position_of,
)
from world.checks.constants import EffectTarget, EffectType, PositionDestination
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.mechanics.effect_handlers import apply_effect


class CreatePositionHandlerTests(TestCase):
    """Tests for the CREATE_POSITION effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="CPHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.start = Position.objects.create(room=self.room, name="start")
        place_in_position(self.char, self.start)
        self.consequence = ConsequenceFactory()

    def test_create_position_carves_and_connects(self) -> None:
        """CREATE_POSITION creates a new named position and connects it to the actor's position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="floating platform",
            position_connect_from_actor=True,
            position_place_occupant=False,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        new = Position.objects.get(room=self.room, name="floating platform")
        self.assertIsNotNone(edge_between(position_of(self.char), new))

    def test_create_position_places_occupant(self) -> None:
        """CREATE_POSITION with position_place_occupant=True moves SELF into the new position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="cloud",
            position_place_occupant=True,
            position_connect_from_actor=False,
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertEqual(position_of(self.char).name, "cloud")

    def test_create_position_returns_created_instance(self) -> None:
        """CREATE_POSITION result carries the new Position as created_instance."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="rampart",
            position_connect_from_actor=False,
            position_place_occupant=False,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertIsInstance(result.created_instance, Position)
        self.assertEqual(result.created_instance.name, "rampart")

    def test_create_position_no_connect_when_flag_false(self) -> None:
        """CREATE_POSITION with position_connect_from_actor=False does not create an edge."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="island",
            position_connect_from_actor=False,
            position_place_occupant=False,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        new = Position.objects.get(room=self.room, name="island")
        self.assertIsNone(edge_between(self.start, new))


class MoveToPositionHandlerTests(TestCase):
    """Tests for the MOVE_TO_POSITION effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="MTHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.other = CharacterFactory(location=self.room)
        self.actor_pos = Position.objects.create(room=self.room, name="actor_spot")
        self.other_pos = Position.objects.create(room=self.room, name="other_spot")
        self.balcony = Position.objects.create(room=self.room, name="balcony")
        place_in_position(self.char, self.actor_pos)
        place_in_position(self.other, self.other_pos)
        self.consequence = ConsequenceFactory()

    def test_move_actor_position_pull(self) -> None:
        """MOVE_TO_POSITION with ACTOR_POSITION pulls TARGET to the actor's position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.ACTOR_POSITION,
            target=EffectTarget.TARGET,
        )
        apply_effect(effect, ResolutionContext(character=self.char, target=self.other))
        self.assertEqual(position_of(self.other).pk, position_of(self.char).pk)

    def test_move_named(self) -> None:
        """MOVE_TO_POSITION with NAMED moves SELF to the named position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.NAMED,
            position_name="balcony",
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertEqual(position_of(self.char).name, "balcony")

    def test_move_unresolvable_destination_returns_unapplied(self) -> None:
        """MOVE_TO_POSITION with a NAMED position that does not exist returns applied=False."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.NAMED,
            position_name="nonexistent_position",
            target=EffectTarget.SELF,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)
