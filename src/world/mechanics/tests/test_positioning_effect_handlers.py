"""Tests for CREATE_POSITION, MOVE_TO_POSITION, GRANT_FLIGHT, and REMOVE_FLIGHT effect handlers.

Built using setUp (not setUpTestData) — Evennia ObjectDB instances (DbHolder)
are not deepcopyable and would break setUpTestData.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.areas.positioning.constants import PositionKind
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
from world.mechanics.factories import AerialPropertyFactory
from world.mechanics.models import ObjectProperty


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


class SeverEdgeHandlerTests(TestCase):
    """Tests for the SEVER_EDGE effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.positioning.services import connect_positions

        self.room = create_object("typeclasses.rooms.Room", key="SEHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.pos_a = Position.objects.create(room=self.room, name="courtyard")
        self.pos_b = Position.objects.create(room=self.room, name="gate")
        connect_positions(self.pos_a, self.pos_b)
        place_in_position(self.char, self.pos_a)
        self.consequence = ConsequenceFactory()

    def test_sever_removes_existing_edge(self) -> None:
        """SEVER_EDGE removes the edge between two named positions."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.SEVER_EDGE,
            position_name="courtyard",
            position_name_b="gate",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertIsNone(edge_between(self.pos_a, self.pos_b))

    def test_sever_skips_when_no_edge(self) -> None:
        """SEVER_EDGE returns applied=False when there is no edge to sever."""
        from world.areas.positioning.services import disconnect_positions

        disconnect_positions(self.pos_a, self.pos_b)
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.SEVER_EDGE,
            position_name="courtyard",
            position_name_b="gate",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)

    def test_sever_skips_when_endpoint_missing(self) -> None:
        """SEVER_EDGE returns applied=False when a named position does not exist."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.SEVER_EDGE,
            position_name="courtyard",
            position_name_b="nonexistent_position",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)


class ConnectEdgeHandlerTests(TestCase):
    """Tests for the CONNECT_EDGE effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="CEHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.pos_a = Position.objects.create(room=self.room, name="tower")
        self.pos_b = Position.objects.create(room=self.room, name="bridge")
        place_in_position(self.char, self.pos_a)
        self.consequence = ConsequenceFactory()

    def test_connect_creates_missing_edge(self) -> None:
        """CONNECT_EDGE creates an edge between two unconnected named positions."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CONNECT_EDGE,
            position_name="tower",
            position_name_b="bridge",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertIsNotNone(edge_between(self.pos_a, self.pos_b))

    def test_connect_idempotent_already_connected(self) -> None:
        """CONNECT_EDGE returns applied=True even when the edge already exists."""
        from world.areas.positioning.services import connect_positions

        connect_positions(self.pos_a, self.pos_b)
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CONNECT_EDGE,
            position_name="tower",
            position_name_b="bridge",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertIsNotNone(edge_between(self.pos_a, self.pos_b))

    def test_connect_skips_when_endpoint_missing(self) -> None:
        """CONNECT_EDGE returns applied=False when a named position does not exist."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CONNECT_EDGE,
            position_name="tower",
            position_name_b="nonexistent_position",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)


class GrantFlightHandlerTests(TestCase):
    """Tests for the GRANT_FLIGHT effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        AerialPropertyFactory()
        self.room = create_object("typeclasses.rooms.Room", key="GFHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.ground = Position.objects.create(
            room=self.room, name="ground", kind=PositionKind.PRIMARY
        )
        place_in_position(self.char, self.ground)
        self.consequence = ConsequenceFactory()

    def test_grant_flight_moves_to_aerial_position(self) -> None:
        """GRANT_FLIGHT places the character in an AERIAL position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.GRANT_FLIGHT,
            target=EffectTarget.SELF,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertEqual(position_of(self.char).kind, PositionKind.AERIAL)

    def test_grant_flight_sets_aerial_property(self) -> None:
        """GRANT_FLIGHT sets the 'aerial' ObjectProperty on the character."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.GRANT_FLIGHT,
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(
            ObjectProperty.objects.filter(object=self.char, property__name="aerial").exists()
        )


class RemoveFlightHandlerTests(TestCase):
    """Tests for the REMOVE_FLIGHT effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.positioning.services import enter_aerial

        AerialPropertyFactory()
        self.room = create_object("typeclasses.rooms.Room", key="RFHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.ground = Position.objects.create(
            room=self.room, name="ground", kind=PositionKind.PRIMARY
        )
        place_in_position(self.char, self.ground)
        enter_aerial(self.char)
        self.consequence = ConsequenceFactory()

    def test_remove_flight_returns_to_ground_position(self) -> None:
        """REMOVE_FLIGHT returns the character to a ground (non-AERIAL) position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.REMOVE_FLIGHT,
            target=EffectTarget.SELF,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertNotEqual(position_of(self.char).kind, PositionKind.AERIAL)

    def test_remove_flight_clears_aerial_property(self) -> None:
        """REMOVE_FLIGHT removes the 'aerial' ObjectProperty from the character."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.REMOVE_FLIGHT,
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(
            ObjectProperty.objects.filter(object=self.char, property__name="aerial").exists()
        )
