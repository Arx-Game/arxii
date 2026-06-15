"""Tests for the technique_can_reach wrapper (Task 3 / #533).

technique_can_reach(attacker, technique, target) -> bool

Lenient when either combatant is unplaced (no Position row). Delegates to
position_reachable when both are placed.

Built in setUp rather than setUpTestData: factories create Evennia ObjectDB instances
(DbHolder — not deepcopyable), which would break setUpTestData's deepcopy.
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.services import (
    connect_positions,
    create_position,
    place_in_position,
)
from world.combat.reach import technique_can_reach
from world.magic.constants import TechniqueReach
from world.magic.factories import TechniqueFactory


class TechniqueCanReachSameTechniqueTests(TestCase):
    """SAME technique: both placed at same position → True; different position → False."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="CanReachSameRoom", nohome=True)
        self.pos_a = create_position(self.room, "pos_a")
        self.pos_b = create_position(self.room, "pos_b")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)

        self.attacker = create_object(
            "typeclasses.characters.Character",
            key="Attacker",
            location=self.room,
            nohome=True,
        )
        self.target = create_object(
            "typeclasses.characters.Character",
            key="Target",
            location=self.room,
            nohome=True,
        )
        self.technique = TechniqueFactory(reach=TechniqueReach.SAME)

    def test_same_position_same_reach_returns_true(self) -> None:
        place_in_position(self.attacker, self.pos_a)
        place_in_position(self.target, self.pos_a)
        self.assertTrue(technique_can_reach(self.attacker, self.technique, self.target))

    def test_different_position_same_reach_returns_false(self) -> None:
        place_in_position(self.attacker, self.pos_a)
        place_in_position(self.target, self.pos_b)
        self.assertFalse(technique_can_reach(self.attacker, self.technique, self.target))


class TechniqueCanReachAdjacentTechniqueTests(TestCase):
    """ADJACENT technique: across a passable edge → True."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="CanReachAdjRoom", nohome=True)
        self.pos_a = create_position(self.room, "adj_pos_a")
        self.pos_b = create_position(self.room, "adj_pos_b")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)

        self.attacker = create_object(
            "typeclasses.characters.Character",
            key="AdjAttacker",
            location=self.room,
            nohome=True,
        )
        self.target = create_object(
            "typeclasses.characters.Character",
            key="AdjTarget",
            location=self.room,
            nohome=True,
        )
        self.technique = TechniqueFactory(reach=TechniqueReach.ADJACENT)

    def test_adjacent_passable_edge_returns_true(self) -> None:
        place_in_position(self.attacker, self.pos_a)
        place_in_position(self.target, self.pos_b)
        self.assertTrue(technique_can_reach(self.attacker, self.technique, self.target))


class TechniqueCanReachLenientTests(TestCase):
    """When either combatant is unplaced, technique_can_reach returns True (lenient)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="CanReachLenientRoom", nohome=True)
        self.pos_a = create_position(self.room, "lenient_pos_a")
        self.pos_b = create_position(self.room, "lenient_pos_b")

        self.attacker = create_object(
            "typeclasses.characters.Character",
            key="LenientAttacker",
            location=self.room,
            nohome=True,
        )
        self.target = create_object(
            "typeclasses.characters.Character",
            key="LenientTarget",
            location=self.room,
            nohome=True,
        )
        self.technique = TechniqueFactory(reach=TechniqueReach.SAME)

    def test_attacker_unplaced_returns_true(self) -> None:
        """Attacker has no position; target is placed. Should be lenient → True."""
        place_in_position(self.target, self.pos_b)
        self.assertTrue(technique_can_reach(self.attacker, self.technique, self.target))

    def test_target_unplaced_returns_true(self) -> None:
        """Target has no position; attacker is placed. Should be lenient → True."""
        place_in_position(self.attacker, self.pos_a)
        self.assertTrue(technique_can_reach(self.attacker, self.technique, self.target))

    def test_both_unplaced_returns_true(self) -> None:
        """Neither is placed. Should be lenient → True."""
        self.assertTrue(technique_can_reach(self.attacker, self.technique, self.target))
