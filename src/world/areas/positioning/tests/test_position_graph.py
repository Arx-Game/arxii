"""Tests for position_graph() — the tactical-map node+edge graph (#2006)."""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.constants import PositionKind, RampartCrackState
from world.areas.positioning.factories import (
    PositionEdgeFactory,
    PositionFactory,
    RampartElementProfileFactory,
    RampartFactory,
)
from world.areas.positioning.services import position_graph
from world.mechanics.factories import ChallengeInstanceFactory, ChallengeTemplateFactory


class PositionGraphTests(TestCase):
    def test_empty_room_returns_empty_graph(self):
        from evennia import create_object

        room = create_object("typeclasses.rooms.Room", key="Empty Room", nohome=True)
        graph = position_graph(room)
        self.assertEqual(graph.nodes, [])
        self.assertEqual(graph.edges, [])

    def test_node_carries_kind_elevation_and_layout(self):
        anchor = PositionFactory(kind=PositionKind.PRIMARY)
        elevated = PositionFactory(
            room=anchor.room,
            kind=PositionKind.ELEVATED,
            elevation_anchor=anchor,
            layout_x=4,
            layout_y=7,
        )
        graph = position_graph(anchor.room)
        node_by_id = {n.id: n for n in graph.nodes}

        self.assertEqual(node_by_id[anchor.pk].kind, PositionKind.PRIMARY)
        self.assertIsNone(node_by_id[anchor.pk].elevation_anchor_id)
        self.assertEqual(node_by_id[elevated.pk].elevation_anchor_id, anchor.pk)
        self.assertEqual(node_by_id[elevated.pk].layout_x, 4)
        self.assertEqual(node_by_id[elevated.pk].layout_y, 7)

    def test_open_edge_has_no_gating_name(self):
        edge = PositionEdgeFactory(is_passable=True)
        graph = position_graph(edge.position_a.room)
        self.assertEqual(len(graph.edges), 1)
        info = graph.edges[0]
        self.assertTrue(info.is_passable)
        self.assertIsNone(info.gating_challenge_name)

    def test_impassable_edge_is_included(self):
        edge = PositionEdgeFactory(is_passable=False)
        graph = position_graph(edge.position_a.room)
        self.assertEqual(len(graph.edges), 1)
        self.assertFalse(graph.edges[0].is_passable)

    def test_gated_edge_carries_challenge_name(self):
        template = ChallengeTemplateFactory(name="Cross the Chasm")
        instance = ChallengeInstanceFactory(template=template)
        edge = PositionEdgeFactory(gating_challenge=instance)
        graph = position_graph(edge.position_a.room)
        self.assertEqual(graph.edges[0].gating_challenge_name, "Cross the Chasm")

    def test_edge_appears_exactly_once(self):
        """Regression: edges must not be double-counted across position_a/position_b."""
        edge = PositionEdgeFactory()
        graph = position_graph(edge.position_a.room)
        self.assertEqual(len(graph.edges), 1)

    def test_uncovered_position_has_null_rampart_fields(self):
        position = PositionFactory()
        graph = position_graph(position.room)
        node = graph.nodes[0]
        self.assertIsNone(node.rampart_element)
        self.assertIsNone(node.rampart_integrity)
        self.assertIsNone(node.rampart_max_integrity)
        self.assertIsNone(node.rampart_crack_state)

    def test_covered_position_carries_rampart_fields(self):
        """#2209: a position with a Rampart surfaces element/integrity/crack_state."""
        profile = RampartElementProfileFactory(name="Stone")
        position = PositionFactory()
        RampartFactory(position=position, element_profile=profile, integrity=20, max_integrity=24)

        graph = position_graph(position.room)
        node = graph.nodes[0]

        self.assertEqual(node.rampart_element, "Stone")
        self.assertEqual(node.rampart_integrity, 20)
        self.assertEqual(node.rampart_max_integrity, 24)
        self.assertEqual(node.rampart_crack_state, RampartCrackState.INTACT)
