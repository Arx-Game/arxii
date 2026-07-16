"""Tests for round-tick expiry of conjured obstacles (#2019)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import PositionEdge
from world.areas.positioning.services import create_conjured_obstacle, expire_obstacle_rounds
from world.character_sheets.factories import CharacterSheetFactory


class RoundTickExpiryTest(TestCase):
    """expire_obstacle_rounds decrements duration and restores at 0 (#2019)."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="room")
        self.pos_a = PositionFactory(room=self.room, name="alpha")
        self.pos_b = PositionFactory(room=self.room, name="bravo")
        self.sheet = CharacterSheetFactory()

    def test_expire_decrements_duration(self) -> None:
        """Each expiry tick decrements duration_rounds by 1."""
        edge = create_conjured_obstacle(
            self.pos_a, self.pos_b, caster_sheet=self.sheet, duration_rounds=3
        )
        expire_obstacle_rounds(self.room)
        edge.refresh_from_db()
        self.assertEqual(edge.duration_rounds, 2)
        self.assertFalse(edge.is_passable)

    def test_expire_restores_at_zero(self) -> None:
        """At 0, the obstacle is restored to passable."""
        edge = create_conjured_obstacle(
            self.pos_a, self.pos_b, caster_sheet=self.sheet, duration_rounds=1
        )
        expire_obstacle_rounds(self.room)
        edge.refresh_from_db()
        self.assertTrue(edge.is_passable)
        self.assertIsNone(edge.duration_rounds)
        self.assertIsNone(edge.created_by_sheet)

    def test_expire_skips_staff_edges(self) -> None:
        """Staff-authored edges (null duration_rounds) are never decremented."""
        from world.areas.positioning.services import connect_positions

        connect_positions(self.pos_a, self.pos_b, is_passable=False)
        expire_obstacle_rounds(self.room)
        edge = PositionEdge.objects.get(position_a=self.pos_a, position_b=self.pos_b)
        self.assertFalse(edge.is_passable)
        self.assertIsNone(edge.duration_rounds)
