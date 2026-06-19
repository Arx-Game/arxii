"""Tests for the aerial-layer lifecycle: enter_aerial / leave_aerial.

Uses setUp (not setUpTestData): Evennia ObjectDB instances (DbHolder) are not
deepcopyable and would break setUpTestData's copy step.
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    enter_aerial,
    force_move_to_position,
    leave_aerial,
    move_to_position,
    place_in_position,
    position_of,
)
from world.mechanics.factories import AerialPropertyFactory, ChallengeInstanceFactory
from world.mechanics.models import ObjectProperty


class AerialLifecycleTests(TestCase):
    """Full lifecycle tests for enter_aerial / leave_aerial."""

    def setUp(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CharacterFactory
        from world.areas.positioning.services import connect_positions, create_position

        # Aerial property — idempotent via django_get_or_create on name.
        self.aerial_prop = AerialPropertyFactory()

        # Room + ground graph: courtyard <-(gated)-> balcony
        self.room = create_object("typeclasses.rooms.Room", key="AerialTestRoom", nohome=True)

        self.courtyard = create_position(self.room, "courtyard", kind=PositionKind.PRIMARY)
        self.balcony = create_position(self.room, "balcony")

        challenge = ChallengeInstanceFactory(location=self.room, target_object=self.room)
        connect_positions(self.courtyard, self.balcony, gating_challenge=challenge)

        # Two characters placed in the room.
        self.char = CharacterFactory(location=self.room)
        self.other = CharacterFactory(location=self.room)

        place_in_position(self.char, self.courtyard)
        place_in_position(self.other, self.courtyard)

    def test_takeoff_materializes_layer_and_lifts(self) -> None:
        """enter_aerial moves char to AERIAL twin and sets aerial ObjectProperty."""
        enter_aerial(self.char)
        pos = position_of(self.char)
        self.assertEqual(pos.kind, PositionKind.AERIAL)
        self.assertEqual(pos.elevation_anchor_id, self.courtyard.pk)
        self.assertTrue(
            ObjectProperty.objects.filter(object=self.char, property=self.aerial_prop).exists()
        )

    def test_horizontal_flight_over_gated_edge(self) -> None:
        """Aerial move to the twin above the far side of a gated edge must not raise."""
        enter_aerial(self.char)
        above_balcony = Position.objects.get(room=self.room, name="Above balcony")
        move_to_position(self.char, above_balcony)  # must NOT raise
        self.assertEqual(position_of(self.char).pk, above_balcony.pk)

    def test_descend_to_anchor(self) -> None:
        """leave_aerial returns char to elevation_anchor and clears aerial property."""
        enter_aerial(self.char)
        above_balcony = Position.objects.get(room=self.room, name="Above balcony")
        force_move_to_position(self.char, above_balcony)
        leave_aerial(self.char)
        self.assertEqual(position_of(self.char).pk, self.balcony.pk)
        self.assertFalse(
            ObjectProperty.objects.filter(object=self.char, property=self.aerial_prop).exists()
        )

    def test_layer_torn_down_only_when_last_flyer_lands(self) -> None:
        """Aerial layer persists while any flyer remains; torn down when all land."""
        enter_aerial(self.char)
        enter_aerial(self.other)

        leave_aerial(self.char)
        # One flyer remains — layer must still exist.
        self.assertTrue(Position.objects.filter(room=self.room, kind=PositionKind.AERIAL).exists())

        leave_aerial(self.other)
        # Last flyer landed — layer must be gone.
        self.assertFalse(Position.objects.filter(room=self.room, kind=PositionKind.AERIAL).exists())

    def test_severed_anchor_falls_to_primary(self) -> None:
        """When elevation_anchor is None, leave_aerial falls to the PRIMARY position."""
        enter_aerial(self.char)
        above = position_of(self.char)
        above.elevation_anchor = None
        above.save(update_fields=["elevation_anchor"])

        leave_aerial(self.char)
        self.assertEqual(position_of(self.char).kind, PositionKind.PRIMARY)
