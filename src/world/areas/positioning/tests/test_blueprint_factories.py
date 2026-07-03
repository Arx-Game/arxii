"""Tests for blueprint FactoryBoy factories and the tavern_blueprint() seed helper.

TDD: test written RED (factories absent), then GREEN after factories are added.
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.models import (
    BlueprintEdge,
    BlueprintPosition,
    Position,
    PositionBlueprint,
    PositionEdge,
)


class PositionBlueprintFactoryTests(TestCase):
    def test_creates_blueprint_with_unique_name(self):
        from world.areas.positioning.factories import PositionBlueprintFactory

        bp1 = PositionBlueprintFactory()
        bp2 = PositionBlueprintFactory()
        self.assertIsInstance(bp1, PositionBlueprint)
        self.assertNotEqual(bp1.name, bp2.name)

    def test_creates_blueprint_with_explicit_name(self):
        from world.areas.positioning.factories import PositionBlueprintFactory

        bp = PositionBlueprintFactory(name="Custom Blueprint")
        self.assertEqual(bp.name, "Custom Blueprint")

    def test_blueprint_is_persisted(self):
        from world.areas.positioning.factories import PositionBlueprintFactory

        bp = PositionBlueprintFactory()
        self.assertTrue(PositionBlueprint.objects.filter(pk=bp.pk).exists())


class BlueprintPositionFactoryTests(TestCase):
    def test_creates_blueprint_position(self):
        from world.areas.positioning.factories import BlueprintPositionFactory

        pos = BlueprintPositionFactory()
        self.assertIsInstance(pos, BlueprintPosition)
        self.assertIsNotNone(pos.blueprint_id)

    def test_creates_with_explicit_blueprint(self):
        from world.areas.positioning.factories import (
            BlueprintPositionFactory,
            PositionBlueprintFactory,
        )

        bp = PositionBlueprintFactory()
        pos = BlueprintPositionFactory(blueprint=bp)
        self.assertEqual(pos.blueprint_id, bp.pk)

    def test_sequence_yields_unique_names_within_same_blueprint(self):
        from world.areas.positioning.factories import (
            BlueprintPositionFactory,
            PositionBlueprintFactory,
        )

        bp = PositionBlueprintFactory()
        pos1 = BlueprintPositionFactory(blueprint=bp)
        pos2 = BlueprintPositionFactory(blueprint=bp)
        self.assertNotEqual(pos1.name, pos2.name)

    def test_position_is_persisted(self):
        from world.areas.positioning.factories import BlueprintPositionFactory

        pos = BlueprintPositionFactory()
        self.assertTrue(BlueprintPosition.objects.filter(pk=pos.pk).exists())


class BlueprintEdgeFactoryTests(TestCase):
    def test_creates_blueprint_edge(self):
        from world.areas.positioning.factories import BlueprintEdgeFactory

        edge = BlueprintEdgeFactory()
        self.assertIsInstance(edge, BlueprintEdge)
        self.assertIsNotNone(edge.pk)

    def test_canonical_order_enforced(self):
        from world.areas.positioning.factories import BlueprintEdgeFactory

        edge = BlueprintEdgeFactory()
        self.assertLess(edge.position_a_id, edge.position_b_id)

    def test_both_positions_in_same_blueprint(self):
        from world.areas.positioning.factories import BlueprintEdgeFactory

        edge = BlueprintEdgeFactory()
        self.assertEqual(edge.position_a.blueprint_id, edge.position_b.blueprint_id)
        self.assertEqual(edge.blueprint_id, edge.position_a.blueprint_id)


class TavernBlueprintTests(TestCase):
    """Integration test: tavern_blueprint() → instantiate_blueprint() → live graph."""

    # setUp (not setUpTestData): Evennia create_object uses SharedMemoryModel/idmapper;
    # fixtures created in setUpTestData get copy.Error(DbHolder) under CI shard runs.
    def setUp(self):
        from evennia import create_object

        from world.areas.positioning.factories import tavern_blueprint
        from world.areas.positioning.services import instantiate_blueprint

        self.room = create_object("typeclasses.rooms.Room", key="TestTavern", nohome=True)
        self.blueprint = tavern_blueprint()
        self.positions = instantiate_blueprint(self.blueprint, self.room)

    def test_blueprint_has_three_positions(self):
        self.assertEqual(
            self.blueprint.positions.count(),
            3,
            "tavern_blueprint() must have exactly 3 BlueprintPositions",
        )

    def test_blueprint_position_names(self):
        names = set(self.blueprint.positions.values_list("name", flat=True))
        self.assertEqual(names, {"Hearth", "Bar", "Doorway"})

    def test_blueprint_has_expected_edges(self):
        # Hearth↔Bar and Bar↔Doorway
        self.assertEqual(self.blueprint.edges.count(), 2)

    def test_instantiate_creates_three_live_positions(self):
        live_names = {p.name for p in self.positions}
        self.assertEqual(live_names, {"Hearth", "Bar", "Doorway"})

    def test_instantiate_creates_live_edges(self):
        edge_count = PositionEdge.objects.filter(position_a__room=self.room).count()
        self.assertEqual(edge_count, 2)

    def test_live_positions_are_in_correct_room(self):
        for pos in self.positions:
            self.assertIsInstance(pos, Position)
            self.assertEqual(pos.room_id, self.room.pk)

    def test_tavern_blueprint_is_idempotent(self):
        """Calling tavern_blueprint() twice returns the same DB row (get_or_create semantics)."""
        from world.areas.positioning.factories import tavern_blueprint

        bp2 = tavern_blueprint()
        self.assertEqual(self.blueprint.pk, bp2.pk)


class RopeBridgeBlueprintTests(TestCase):
    """Integration test: rope_bridge_blueprint() → instantiate_blueprint() → gated crossing."""

    def setUp(self):
        from evennia import create_object

        from world.areas.positioning.factories import rope_bridge_blueprint
        from world.areas.positioning.services import instantiate_blueprint

        self.room = create_object("typeclasses.rooms.Room", key="TestRopeBridge", nohome=True)
        self.blueprint = rope_bridge_blueprint()
        self.positions = instantiate_blueprint(self.blueprint, self.room)

    def test_blueprint_has_two_positions(self):
        self.assertEqual(self.blueprint.positions.count(), 2)

    def test_blueprint_edge_is_gated(self):
        edge = self.blueprint.edges.get()
        self.assertIsNotNone(edge.gating_challenge_template_id)

    def test_gated_template_has_a_resolvable_approach(self):
        edge = self.blueprint.edges.get()
        self.assertTrue(edge.gating_challenge_template.approaches.exists())

    def test_instantiate_produces_live_gated_edge(self):
        from world.areas.positioning.services import edge_between

        near, far = sorted(self.positions, key=lambda p: p.name)
        live_edge = edge_between(near, far)
        self.assertIsNotNone(live_edge.gating_challenge_id)
        self.assertTrue(live_edge.gating_challenge.is_active)

    def test_rope_bridge_blueprint_is_idempotent(self):
        from world.areas.positioning.factories import rope_bridge_blueprint

        bp2 = rope_bridge_blueprint()
        self.assertEqual(self.blueprint.pk, bp2.pk)
