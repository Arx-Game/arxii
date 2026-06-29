"""Tests for move_position and create_obstacle effect handlers (#1584).

SQLite-safe: no apply_condition / DISTINCT ON in this path.
"""

from dataclasses import dataclass

from django.test import TestCase

from world.areas.positioning.factories import ObjectPositionFactory, PositionFactory
from world.areas.positioning.models import PositionEdge
from world.areas.positioning.services import edge_between, position_of
from world.magic.services.effect_handlers import create_obstacle, move_position


@dataclass
class _MovePayload:
    target: object
    destination_position_id: int


@dataclass
class _ObstaclePayload:
    position_a_id: int
    position_b_id: int
    blocks_flight: bool = False


class MovePositionHandlerTests(TestCase):
    """move_position relocates the target objectdb to the destination position."""

    def test_move_position_relocates_object(self) -> None:
        a = PositionFactory()
        b = PositionFactory(room=a.room)
        # Place the objectdb in the shared room at position a.
        op = ObjectPositionFactory(position=a)
        obj = op.objectdb
        # Confirm objectdb is in the right room (same room as b).
        self.assertEqual(obj.db_location_id, b.room_id)

        move_position(payload=_MovePayload(target=obj, destination_position_id=b.pk))

        self.assertEqual(position_of(obj), b)


class CreateObstacleHandlerTests(TestCase):
    """create_obstacle makes the edge between two positions impassable."""

    def test_create_obstacle_marks_edge_impassable(self) -> None:
        a = PositionFactory()
        b = PositionFactory(room=a.room)

        create_obstacle(payload=_ObstaclePayload(position_a_id=a.pk, position_b_id=b.pk))

        edge = edge_between(a, b)
        self.assertIsNotNone(edge)
        self.assertIsInstance(edge, PositionEdge)
        self.assertFalse(edge.is_passable)

    def test_create_obstacle_with_blocks_flight(self) -> None:
        a = PositionFactory()
        b = PositionFactory(room=a.room)

        create_obstacle(
            payload=_ObstaclePayload(position_a_id=a.pk, position_b_id=b.pk, blocks_flight=True)
        )

        edge = edge_between(a, b)
        self.assertIsNotNone(edge)
        self.assertFalse(edge.is_passable)
        self.assertTrue(edge.blocks_flight)
