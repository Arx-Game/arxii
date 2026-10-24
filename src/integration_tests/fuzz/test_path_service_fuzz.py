"""Fuzz: the path service never routes a mover through a crossing it cannot make (#4607).

Hypothesis builds a random connected room of 3 to 8 positions. Every edge is open, a
hard seal, a wall with an active way past it, or a wall whose way past was already
taken (an inactive challenge), and may block flight. Sometimes the aerial layer is
raised over it. For every pair of positions and a random traversal, the properties are
the ones movers rely on: a route starts at the origin and ends at the goal, every step
crosses an edge that ``edge_crossing_cost`` opens to that mover, ``step_costs`` agrees
with it, and only a flier ever stands on an aerial position. On the ground alone, the
positions a walker can route to are exactly the ones ``reachable_positions`` (the walker
rule's own search) finds.
"""

from __future__ import annotations

from itertools import pairwise

from evennia import create_object
from hypothesis import given, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    create_position,
    edge_between,
    edge_crossing_cost,
    find_path,
    materialize_aerial_layer,
    place_in_position,
    reachable_positions,
    step_costs,
)
from world.mechanics.factories import ChallengeInstanceFactory

OPEN, HARD_SEAL, GATED, CLIMBED = "open", "hard_seal", "gated", "climbed"
edge_states = st.sampled_from([OPEN, HARD_SEAL, GATED, CLIMBED])
traversals = st.sampled_from(CreatureTraversal.values)


@st.composite
def rooms(draw: st.DrawFn) -> tuple[int, list[tuple[int, int, str, bool]]]:
    """A position count and its edges: a chain keeps the graph connected, plus extras."""
    count = draw(st.integers(min_value=3, max_value=8))
    pairs = {(i, i + 1) for i in range(count - 1)}
    extras = draw(
        st.lists(
            st.tuples(st.integers(0, count - 1), st.integers(0, count - 1)).filter(
                lambda p: p[0] != p[1]
            ),
            max_size=count,
        )
    )
    pairs |= {tuple(sorted(p)) for p in extras}
    edges = [(a, b, draw(edge_states), draw(st.booleans())) for a, b in sorted(pairs)]
    return count, edges


class PathServiceHoldsItsContract(HypothesisTestCase):
    def build(self, count: int, edges: list[tuple[int, int, str, bool]]) -> list[Position]:
        room = create_object("typeclasses.rooms.Room", key="Fuzz Yard", nohome=True)
        positions = [
            create_position(
                room, f"P{i}", kind=PositionKind.PRIMARY if i == 0 else PositionKind.FEATURE
            )
            for i in range(count)
        ]
        active = ChallengeInstanceFactory(location=room, target_object=room)
        spent = ChallengeInstanceFactory(location=room, target_object=room, is_active=False)
        for a, b, state, blocks_flight in edges:
            here, there = positions[a], positions[b]
            if state == OPEN:
                connect_positions(here, there, blocks_flight=blocks_flight)
                continue
            gate = {HARD_SEAL: None, GATED: active, CLIMBED: spent}[state]
            create_conjured_obstacle(
                here,
                there,
                caster_sheet=None,
                integrity=5,
                gating_challenge=gate,
                blocks_flight=blocks_flight,
            )
        return positions

    @given(rooms(), traversals, st.booleans())
    def test_every_route_crosses_only_open_edges(
        self,
        room: tuple[int, list[tuple[int, int, str, bool]]],
        traversal: str,
        aerial: bool,
    ) -> None:
        ground = self.build(*room)
        if aerial:
            materialize_aerial_layer(ground[0].room)
        everywhere = list(Position.objects.filter(room=ground[0].room).order_by("pk"))
        for origin in ground:
            for goal in everywhere:
                path = find_path(origin, lambda p, goal=goal: p == goal, traversal=traversal)
                if path is None:
                    continue
                self.assertEqual((path[0], path[-1]), (origin, goal))
                expected = []
                for here, there in pairwise(path):
                    edge = edge_between(here, there)
                    self.assertIsNotNone(edge, f"{here.name} to {there.name} has no edge")
                    cost = edge_crossing_cost(edge, traversal)
                    self.assertIsNotNone(cost, f"{traversal} crossed a closed edge")
                    expected.append(cost)
                self.assertEqual(step_costs(path, traversal=traversal), expected)
                if traversal != CreatureTraversal.FLIES:
                    self.assertFalse(any(p.kind == PositionKind.AERIAL for p in path))

    @given(rooms())
    def test_a_walker_routes_to_exactly_what_the_walker_rule_reaches(
        self, room: tuple[int, list[tuple[int, int, str, bool]]]
    ) -> None:
        ground = self.build(*room)
        origin = ground[0]
        walker = create_object("typeclasses.objects.Object", key="walker", location=origin.room)
        place_in_position(walker, origin)
        walks = CreatureTraversal.WALKS
        routed = {
            goal
            for goal in ground
            if find_path(origin, lambda p, goal=goal: p == goal, traversal=walks) is not None
        }
        self.assertEqual(routed, reachable_positions(walker) | {origin})
