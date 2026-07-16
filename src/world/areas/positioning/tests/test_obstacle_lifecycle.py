"""Tests for conjured obstacle lifecycle (#2019)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import PositionEdge
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    teardown_conjured_obstacles,
)
from world.character_sheets.factories import CharacterSheetFactory


class ObstacleLifecycleTest(TestCase):
    """Conjured obstacles get duration, owner, and restore-on-teardown (#2019)."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="test_room")
        self.pos_a = PositionFactory(room=self.room, name="alpha")
        self.pos_b = PositionFactory(room=self.room, name="bravo")
        self.sheet = CharacterSheetFactory()

    def test_conjured_obstacle_has_duration_and_owner(self) -> None:
        """create_conjured_obstacle sets is_passable=False + duration + owner."""
        edge = create_conjured_obstacle(
            self.pos_a, self.pos_b, caster_sheet=self.sheet, duration_rounds=3
        )
        self.assertFalse(edge.is_passable)
        self.assertEqual(edge.duration_rounds, 3)
        self.assertEqual(edge.created_by_sheet, self.sheet)

    def test_conjured_obstacle_on_existing_edge_preserves_edge(self) -> None:
        """Barricading an existing passable edge updates it to impassable."""
        original = connect_positions(self.pos_a, self.pos_b, is_passable=True)
        edge = create_conjured_obstacle(
            self.pos_a, self.pos_b, caster_sheet=self.sheet, duration_rounds=3
        )
        self.assertEqual(edge.pk, original.pk)
        self.assertFalse(edge.is_passable)

    def test_teardown_restores_conjured_obstacles(self) -> None:
        """teardown_conjured_obstacles restores conjured edges to passable."""
        create_conjured_obstacle(self.pos_a, self.pos_b, caster_sheet=self.sheet, duration_rounds=5)
        teardown_conjured_obstacles(self.room)
        edge = PositionEdge.objects.get(position_a=self.pos_a, position_b=self.pos_b)
        self.assertTrue(edge.is_passable)
        self.assertIsNone(edge.duration_rounds)
        self.assertIsNone(edge.created_by_sheet)

    def test_teardown_preserves_staff_edges(self) -> None:
        """Staff-authored edges (null created_by_sheet) are not touched."""
        connect_positions(self.pos_a, self.pos_b, is_passable=False)
        teardown_conjured_obstacles(self.room)
        edge = PositionEdge.objects.get(position_a=self.pos_a, position_b=self.pos_b)
        self.assertFalse(edge.is_passable)
