"""Tests for blueprint authoring service functions.

TDD: tests written first (RED), then services implemented (GREEN).
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.models import BlueprintEdge, BlueprintPosition, PositionBlueprint
from world.areas.positioning.services import (
    add_blueprint_position,
    connect_blueprint_positions,
    create_blueprint,
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
        remove_blueprint(bp)
        self.assertFalse(BlueprintPosition.objects.filter(pk__in=[p1_pk, p2_pk]).exists())
        self.assertFalse(BlueprintEdge.objects.filter(blueprint_id=bp.pk).exists())
