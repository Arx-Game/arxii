"""Tests for PositionBlueprint, BlueprintPosition, and BlueprintEdge models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.areas.positioning.models import BlueprintEdge, BlueprintPosition, PositionBlueprint


class BlueprintModelTests(TestCase):
    def test_blueprint_owns_positions_and_edges(self):
        bp = PositionBlueprint.objects.create(name="Tavern", description="A common room")
        hearth = BlueprintPosition.objects.create(blueprint=bp, name="Hearth")
        bar = BlueprintPosition.objects.create(blueprint=bp, name="Bar")
        lo, hi = sorted([hearth, bar], key=lambda p: p.pk)
        edge = BlueprintEdge.objects.create(blueprint=bp, position_a=lo, position_b=hi)
        self.assertEqual(set(bp.positions.all()), {hearth, bar})
        self.assertEqual(list(bp.edges.all()), [edge])

    def test_blueprint_position_name_unique_per_blueprint(self):
        bp = PositionBlueprint.objects.create(name="Keep")
        BlueprintPosition.objects.create(blueprint=bp, name="Gate")
        with self.assertRaises(IntegrityError):
            BlueprintPosition.objects.create(blueprint=bp, name="Gate")

    def test_blueprint_edge_rejects_non_canonical_order(self):
        bp = PositionBlueprint.objects.create(name="Keep2")
        a = BlueprintPosition.objects.create(blueprint=bp, name="A")
        b = BlueprintPosition.objects.create(blueprint=bp, name="B")
        lo, hi = sorted([a, b], key=lambda p: p.pk)
        edge = BlueprintEdge(blueprint=bp, position_a=hi, position_b=lo)
        with self.assertRaises(ValidationError):
            edge.full_clean()

    def test_blueprint_edge_rejects_cross_blueprint_endpoints(self):
        """An edge's two positions must belong to the same blueprint."""
        bp1 = PositionBlueprint.objects.create(name="Blueprint1")
        bp2 = PositionBlueprint.objects.create(name="Blueprint2")
        a = BlueprintPosition.objects.create(blueprint=bp1, name="NodeA")
        b = BlueprintPosition.objects.create(blueprint=bp2, name="NodeB")
        lo, hi = sorted([a, b], key=lambda p: p.pk)
        edge = BlueprintEdge(blueprint=bp1, position_a=lo, position_b=hi)
        with self.assertRaises(ValidationError):
            edge.full_clean()
