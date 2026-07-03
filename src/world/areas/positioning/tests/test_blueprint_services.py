"""Tests for blueprint authoring service functions.

TDD: tests written first (RED), then services implemented (GREEN).
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.models import (
    BlueprintEdge,
    BlueprintPosition,
    Position,
    PositionBlueprint,
    PositionEdge,
)
from world.areas.positioning.services import (
    add_blueprint_position,
    connect_blueprint_positions,
    create_blueprint,
    instantiate_blueprint,
    place_in_position,
    remove_blueprint,
)


class CreateBlueprintTests(TestCase):
    def test_creates_and_returns_blueprint(self):
        bp = create_blueprint("Tavern")
        self.assertIsInstance(bp, PositionBlueprint)
        self.assertEqual(bp.name, "Tavern")
        self.assertEqual(bp.description, "")
        self.assertTrue(bp.pk)

    def test_creates_blueprint_with_description(self):
        bp = create_blueprint("Forest Clearing", description="An open glade.")
        self.assertEqual(bp.description, "An open glade.")

    def test_blueprint_is_persisted(self):
        bp = create_blueprint("Keep")
        self.assertEqual(PositionBlueprint.objects.get(pk=bp.pk).name, "Keep")


class AddBlueprintPositionTests(TestCase):
    def setUp(self):
        self.bp = create_blueprint("Arena")

    def test_creates_and_returns_blueprint_position(self):
        pos = add_blueprint_position(self.bp, "North Stand")
        self.assertIsInstance(pos, BlueprintPosition)
        self.assertEqual(pos.name, "North Stand")
        self.assertEqual(pos.blueprint, self.bp)

    def test_default_kind_is_feature(self):
        pos = add_blueprint_position(self.bp, "Center Ring")
        self.assertEqual(pos.kind, PositionKind.FEATURE)

    def test_custom_kind_and_description(self):
        pos = add_blueprint_position(
            self.bp, "Altar", kind=PositionKind.ELEVATED, description="A stone altar."
        )
        self.assertEqual(pos.kind, PositionKind.ELEVATED)
        self.assertEqual(pos.description, "A stone altar.")

    def test_position_is_persisted(self):
        pos = add_blueprint_position(self.bp, "Entry")
        self.assertEqual(BlueprintPosition.objects.get(pk=pos.pk).name, "Entry")


class ConnectBlueprintPositionsTests(TestCase):
    def setUp(self):
        self.bp = create_blueprint("Dungeon")
        self.p1 = add_blueprint_position(self.bp, "Gate")
        self.p2 = add_blueprint_position(self.bp, "Hall")
        self.p3 = add_blueprint_position(self.bp, "Vault")

    def test_creates_and_returns_edge(self):
        edge = connect_blueprint_positions(self.p1, self.p2)
        self.assertIsInstance(edge, BlueprintEdge)
        self.assertTrue(edge.pk)

    def test_edge_canonical_order_forward(self):
        """Connecting low-pk→high-pk yields a_id < b_id."""
        lo, hi = sorted([self.p1, self.p2], key=lambda p: p.pk)
        edge = connect_blueprint_positions(lo, hi)
        self.assertLess(edge.position_a_id, edge.position_b_id)

    def test_edge_canonical_order_reversed_args(self):
        """Connecting high-pk→low-pk still yields a_id < b_id (canonical swap)."""
        lo, hi = sorted([self.p1, self.p2], key=lambda p: p.pk)
        edge = connect_blueprint_positions(hi, lo)
        self.assertEqual(edge.position_a_id, lo.pk)
        self.assertEqual(edge.position_b_id, hi.pk)

    def test_edge_blueprint_fk_set_from_endpoints(self):
        edge = connect_blueprint_positions(self.p1, self.p2)
        self.assertEqual(edge.blueprint_id, self.bp.pk)

    def test_edge_is_passable_by_default(self):
        edge = connect_blueprint_positions(self.p1, self.p2)
        self.assertTrue(edge.is_passable)

    def test_edge_is_passable_false(self):
        edge = connect_blueprint_positions(self.p1, self.p2, is_passable=False)
        self.assertFalse(edge.is_passable)

    def test_cross_blueprint_guard_raises_position_error(self):
        other_bp = create_blueprint("Other Blueprint")
        foreign_pos = add_blueprint_position(other_bp, "Outpost")
        with self.assertRaises(PositionError) as ctx:
            connect_blueprint_positions(self.p1, foreign_pos)
        self.assertIn("same blueprint", str(ctx.exception))

    def test_cross_blueprint_guard_reversed_args(self):
        other_bp = create_blueprint("Other Blueprint 2")
        foreign_pos = add_blueprint_position(other_bp, "Tower")
        with self.assertRaises(PositionError):
            connect_blueprint_positions(foreign_pos, self.p1)

    def test_edge_is_persisted(self):
        edge = connect_blueprint_positions(self.p1, self.p2)
        self.assertEqual(BlueprintEdge.objects.get(pk=edge.pk).blueprint_id, self.bp.pk)

    def test_gating_challenge_template_defaults_to_none(self):
        edge = connect_blueprint_positions(self.p1, self.p2)
        self.assertIsNone(edge.gating_challenge_template_id)

    def test_gating_challenge_template_is_set_when_passed(self):
        from world.mechanics.factories import ChallengeTemplateFactory

        template = ChallengeTemplateFactory()
        edge = connect_blueprint_positions(self.p1, self.p2, gating_challenge_template=template)
        self.assertEqual(edge.gating_challenge_template_id, template.pk)


class RoundTripTests(TestCase):
    """Create blueprint → add 3 positions → connect → assert counts."""

    def test_round_trip(self):
        bp = create_blueprint("Round Trip Blueprint")
        p1 = add_blueprint_position(bp, "Alpha")
        p2 = add_blueprint_position(bp, "Beta")
        p3 = add_blueprint_position(bp, "Gamma")
        connect_blueprint_positions(p1, p2)
        connect_blueprint_positions(p2, p3)
        # Refresh to avoid idmapper cache
        bp.refresh_from_db()
        self.assertEqual(bp.positions.count(), 3)
        self.assertEqual(bp.edges.count(), 2)


class RemoveBlueprintTests(TestCase):
    def test_removes_blueprint(self):
        bp = create_blueprint("Doomed")
        pk = bp.pk
        remove_blueprint(bp)
        self.assertFalse(PositionBlueprint.objects.filter(pk=pk).exists())

    def test_cascades_positions_and_edges(self):
        bp = create_blueprint("Cascade Test")
        p1 = add_blueprint_position(bp, "Node1")
        p2 = add_blueprint_position(bp, "Node2")
        connect_blueprint_positions(p1, p2)
        p1_pk, p2_pk = p1.pk, p2.pk
        bp_pk = bp.pk  # capture before delete (bp.pk → None post-delete)
        remove_blueprint(bp)
        self.assertFalse(BlueprintPosition.objects.filter(pk__in=[p1_pk, p2_pk]).exists())
        self.assertFalse(BlueprintEdge.objects.filter(blueprint_id=bp_pk).exists())


class InstantiateBlueprintTests(TestCase):
    """TDD tests for instantiate_blueprint — written RED-first."""

    def setUp(self):
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="TestRoom", nohome=True)
        self.bp = create_blueprint("Tavern")
        self.h = add_blueprint_position(self.bp, "Hearth")
        self.b = add_blueprint_position(self.bp, "Bar")
        connect_blueprint_positions(self.h, self.b)

    def test_instantiate_clones_graph(self):
        positions = instantiate_blueprint(self.bp, self.room)
        self.assertEqual({p.name for p in positions}, {"Hearth", "Bar"})
        self.assertEqual(PositionEdge.objects.filter(position_a__room=self.room).count(), 1)

    def test_instantiate_returns_position_instances(self):
        positions = instantiate_blueprint(self.bp, self.room)
        for pos in positions:
            self.assertIsInstance(pos, Position)
            self.assertEqual(pos.room_id, self.room.pk)

    def test_instantiate_carries_kind_and_description(self):
        bp2 = create_blueprint("Dungeon2")
        add_blueprint_position(bp2, "Altar", kind=PositionKind.ELEVATED, description="Raised dais.")
        from evennia import create_object

        room3 = create_object("typeclasses.rooms.Room", key="Room3", nohome=True)
        positions = instantiate_blueprint(bp2, room3)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].kind, PositionKind.ELEVATED)
        self.assertEqual(positions[0].description, "Raised dais.")

    def test_instantiate_refuses_already_staged(self):
        instantiate_blueprint(self.bp, self.room)
        with self.assertRaises(PositionError) as ctx:
            instantiate_blueprint(self.bp, self.room)
        self.assertIn("already staged", str(ctx.exception))

    def test_replace_refuses_when_occupied(self):
        from evennia import create_object

        room2 = create_object("typeclasses.rooms.Room", key="OccupiedRoom", nohome=True)
        char = create_object(
            "typeclasses.characters.Character", key="TestChar", location=room2, nohome=True
        )
        positions = instantiate_blueprint(self.bp, room2)
        hearth = next(p for p in positions if p.name == "Hearth")
        place_in_position(char, hearth)
        with self.assertRaises(PositionError) as ctx:
            instantiate_blueprint(self.bp, room2, replace=True)
        self.assertIn("occupied", str(ctx.exception))

    def test_replace_succeeds_when_empty(self):
        instantiate_blueprint(self.bp, self.room)
        # No occupants — replace=True should succeed and produce fresh positions.
        positions2 = instantiate_blueprint(self.bp, self.room, replace=True)
        self.assertEqual({p.name for p in positions2}, {"Hearth", "Bar"})
        # Exactly the new set — old positions were deleted and replaced.
        self.assertEqual(Position.objects.filter(room=self.room).count(), 2)

    def test_replace_edge_reproduced(self):
        instantiate_blueprint(self.bp, self.room)
        instantiate_blueprint(self.bp, self.room, replace=True)
        self.assertEqual(PositionEdge.objects.filter(position_a__room=self.room).count(), 1)


class InstantiateBlueprintGatedEdgeTests(TestCase):
    """instantiate_blueprint must mint a live ChallengeInstance for gated edges."""

    def setUp(self):
        from evennia import create_object

        from world.mechanics.factories import ChallengeTemplateFactory

        self.room = create_object("typeclasses.rooms.Room", key="GatedTestRoom", nohome=True)
        self.template = ChallengeTemplateFactory()
        self.bp = create_blueprint("Chasm")
        self.near = add_blueprint_position(self.bp, "Near Side")
        self.far = add_blueprint_position(self.bp, "Far Side")
        self.overlook = add_blueprint_position(self.bp, "Overlook")
        connect_blueprint_positions(self.near, self.far, gating_challenge_template=self.template)
        # Ungated edge in the same blueprint — regression guard for Task 4's change.
        connect_blueprint_positions(self.near, self.overlook)

    def test_cloned_edge_has_live_gating_challenge(self):
        from world.areas.positioning.services import edge_between

        instantiate_blueprint(self.bp, self.room)
        near_live = Position.objects.get(room=self.room, name="Near Side")
        far_live = Position.objects.get(room=self.room, name="Far Side")
        live_edge = edge_between(near_live, far_live)

        self.assertIsNotNone(live_edge)
        self.assertIsNotNone(live_edge.gating_challenge_id)
        self.assertTrue(live_edge.gating_challenge.is_active)
        self.assertEqual(live_edge.gating_challenge.template_id, self.template.pk)
        self.assertEqual(live_edge.gating_challenge.location_id, self.room.pk)

    def test_two_rooms_get_independent_challenge_instances(self):
        from evennia import create_object

        from world.areas.positioning.services import edge_between

        room2 = create_object("typeclasses.rooms.Room", key="GatedTestRoom2", nohome=True)
        instantiate_blueprint(self.bp, self.room)
        instantiate_blueprint(self.bp, room2)

        edge1 = edge_between(
            Position.objects.get(room=self.room, name="Near Side"),
            Position.objects.get(room=self.room, name="Far Side"),
        )
        edge2 = edge_between(
            Position.objects.get(room=room2, name="Near Side"),
            Position.objects.get(room=room2, name="Far Side"),
        )
        self.assertNotEqual(edge1.gating_challenge_id, edge2.gating_challenge_id)

    def test_ungated_edge_in_same_blueprint_stays_ungated(self):
        """Regression guard: gating one edge must not gate its sibling edge."""
        from world.areas.positioning.services import edge_between

        instantiate_blueprint(self.bp, self.room)
        near_live = Position.objects.get(room=self.room, name="Near Side")
        overlook_live = Position.objects.get(room=self.room, name="Overlook")
        ungated_live_edge = edge_between(near_live, overlook_live)

        self.assertIsNotNone(ungated_live_edge)
        self.assertIsNone(ungated_live_edge.gating_challenge_id)
