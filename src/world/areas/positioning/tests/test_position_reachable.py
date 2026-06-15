"""Tests for the position_reachable predicate (Task 3 / #533).

Built in setUp rather than setUpTestData: factories create Evennia ObjectDB instances
(DbHolder — not deepcopyable), which would break setUpTestData's deepcopy.
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.services import (
    connect_positions,
    create_position,
    position_reachable,
)
from world.magic.constants import TechniqueReach


class PositionReachableSameTests(TestCase):
    """SAME reach: only the identical position is reachable."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="ReachSameRoom", nohome=True)
        self.room2 = create_object("typeclasses.rooms.Room", key="ReachSameRoom2", nohome=True)
        self.a = create_position(self.room, "node_a")
        self.b = create_position(self.room, "node_b")
        self.c_other = create_position(self.room2, "node_c_other")
        connect_positions(self.a, self.b, is_passable=True)

    def test_same_position_is_reachable(self) -> None:
        self.assertTrue(position_reachable(self.a, self.a, TechniqueReach.SAME))

    def test_adjacent_position_not_reachable_with_same(self) -> None:
        self.assertFalse(position_reachable(self.a, self.b, TechniqueReach.SAME))

    def test_different_room_not_reachable_with_same(self) -> None:
        self.assertFalse(position_reachable(self.a, self.c_other, TechniqueReach.SAME))


class PositionReachableAdjacentTests(TestCase):
    """ADJACENT reach: same position or one passable edge away."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="ReachAdjRoom", nohome=True)
        self.room2 = create_object("typeclasses.rooms.Room", key="ReachAdjRoom2", nohome=True)
        self.a = create_position(self.room, "adj_a")
        self.b = create_position(self.room, "adj_b")
        self.c = create_position(self.room, "adj_c")  # two hops from a via b
        self.d_other = create_position(self.room2, "adj_d_other")

        connect_positions(self.a, self.b, is_passable=True)
        connect_positions(self.b, self.c, is_passable=True)

    def test_same_position_is_reachable_with_adjacent(self) -> None:
        self.assertTrue(position_reachable(self.a, self.a, TechniqueReach.ADJACENT))

    def test_one_passable_edge_apart_is_reachable(self) -> None:
        self.assertTrue(position_reachable(self.a, self.b, TechniqueReach.ADJACENT))

    def test_two_hops_apart_not_reachable(self) -> None:
        self.assertFalse(position_reachable(self.a, self.c, TechniqueReach.ADJACENT))

    def test_different_room_not_reachable_with_adjacent(self) -> None:
        self.assertFalse(position_reachable(self.a, self.d_other, TechniqueReach.ADJACENT))


class PositionReachableAdjacentImpassableTests(TestCase):
    """ADJACENT reach checks edge existence (not passability for gating).

    Per spec: gating challenges gate MOVEMENT, not reach — an ADJACENT technique
    can strike across a movement-gated edge. But is_passable=False means no edge
    for attack purposes either (it's a wall, not a gate).
    """

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="ReachImpRoom", nohome=True)
        self.a = create_position(self.room, "imp_a")
        self.b = create_position(self.room, "imp_b")
        connect_positions(self.a, self.b, is_passable=False)

    def test_impassable_edge_not_reachable_with_adjacent(self) -> None:
        """An impassable edge (wall) blocks ADJACENT reach — no edge.is_passable."""
        self.assertFalse(position_reachable(self.a, self.b, TechniqueReach.ADJACENT))


class PositionReachableAnyTests(TestCase):
    """ANY reach: any position in the same room."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="ReachAnyRoom", nohome=True)
        self.room2 = create_object("typeclasses.rooms.Room", key="ReachAnyRoom2", nohome=True)
        self.a = create_position(self.room, "any_a")
        self.b = create_position(self.room, "any_b")
        self.c = create_position(self.room, "any_c")  # two hops from a
        self.d_other = create_position(self.room2, "any_d_other")

        connect_positions(self.a, self.b, is_passable=True)
        connect_positions(self.b, self.c, is_passable=True)

    def test_same_position_is_reachable_with_any(self) -> None:
        self.assertTrue(position_reachable(self.a, self.a, TechniqueReach.ANY))

    def test_adjacent_position_is_reachable_with_any(self) -> None:
        self.assertTrue(position_reachable(self.a, self.b, TechniqueReach.ANY))

    def test_two_hops_apart_is_reachable_with_any(self) -> None:
        self.assertTrue(position_reachable(self.a, self.c, TechniqueReach.ANY))

    def test_different_room_not_reachable_with_any(self) -> None:
        self.assertFalse(position_reachable(self.a, self.d_other, TechniqueReach.ANY))


class PositionReachableUnknownReachTests(TestCase):
    """Unknown reach values return False (conservative)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="ReachUnknownRoom", nohome=True)
        self.a = create_position(self.room, "unk_a")
        self.b = create_position(self.room, "unk_b")
        connect_positions(self.a, self.b, is_passable=True)

    def test_unknown_reach_value_returns_false(self) -> None:
        self.assertFalse(position_reachable(self.a, self.b, "teleport"))

    def test_unknown_reach_same_position_returns_false(self) -> None:
        self.assertFalse(position_reachable(self.a, self.a, "teleport"))
