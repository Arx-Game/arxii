"""The path service, the strike reach rule and the one commit point (#4607, slice 2 of #4576).

The yard is A - B - C in a row, plus a detour D joined to A and to C. Each test seals or
gates the B - C edge and asks how a walker, a climber or a flier gets from A to C.

Uses setUp (not setUpTestData): Evennia ObjectDB instances are not deepcopyable.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    disconnect_positions,
    enter_aerial,
    find_path,
    force_move_to_position,
    materialize_aerial_layer,
    move_to_position,
    path_costs_from,
    place_in_position,
    step_costs,
    strike_reaches,
)
from world.combat.constants import StrikeDelivery
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.mechanics.factories import AerialPropertyFactory, ChallengeInstanceFactory


class _Yard(TestCase):
    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="The Yard", nohome=True)
        self.a = PositionFactory(room=self.room, name="A", kind=PositionKind.PRIMARY)
        self.b = PositionFactory(room=self.room, name="B")
        self.c = PositionFactory(room=self.room, name="C")
        self.d = PositionFactory(room=self.room, name="D")
        connect_positions(self.a, self.b)
        connect_positions(self.b, self.c)
        connect_positions(self.a, self.d)
        connect_positions(self.d, self.c)

    def drop_detour(self) -> None:
        disconnect_positions(self.a, self.d)
        disconnect_positions(self.d, self.c)

    def hard_seal(self, *, blocks_flight: bool = False) -> None:
        create_conjured_obstacle(
            self.b, self.c, caster_sheet=None, integrity=10, blocks_flight=blocks_flight
        )

    def gate(self) -> None:
        challenge = ChallengeInstanceFactory(location=self.room, target_object=self.room)
        create_conjured_obstacle(
            self.b, self.c, caster_sheet=None, integrity=10, gating_challenge=challenge
        )

    def path(self, traversal: str, goal: Position | None = None) -> list[Position] | None:
        goal = goal or self.c
        return find_path(self.a, lambda p: p == goal, traversal=traversal)


class FindPathTests(_Yard):
    """The pure branchy search: tie-break, equal-cost detour, climber step costs, origin goal.

    The wall journeys cover each traversal against a wall; these pin the choices a journey
    cannot see, which route is picked when several cost the same.
    """

    def test_walker_takes_the_lower_pk_route_on_a_tie(self) -> None:
        # A-B-C and A-D-C both cost 2 hops in 2 steps; B has the lower pk.
        self.assertEqual(self.path(CreatureTraversal.WALKS), [self.a, self.b, self.c])

    def test_climber_crosses_gated_edge_at_two(self) -> None:
        self.drop_detour()
        self.gate()
        path = self.path(CreatureTraversal.CLIMBS)
        self.assertEqual(path, [self.a, self.b, self.c])
        self.assertEqual(step_costs(path, traversal=CreatureTraversal.CLIMBS), [1, 2])

    def test_climber_prefers_an_open_detour_of_equal_cost(self) -> None:
        # Through the gate costs 1 + 2 = 3; the detour costs 2.
        self.gate()
        self.assertEqual(self.path(CreatureTraversal.LEAPS), [self.a, self.d, self.c])

    def test_held_positions_stop_both_route_searches(self) -> None:
        held = frozenset({self.b.pk, self.d.pk})
        self.assertIsNone(
            find_path(
                self.a,
                lambda position: position == self.c,
                traversal=CreatureTraversal.WALKS,
                stop_at=held,
            )
        )
        costs = path_costs_from(self.a, traversal=CreatureTraversal.WALKS, stop_at=held)
        self.assertEqual(costs, {self.a.pk: 0, self.b.pk: 1, self.d.pk: 1})

    def test_origin_satisfies_goal(self) -> None:
        self.assertEqual(self.path(CreatureTraversal.WALKS, goal=self.a), [self.a])


class StaleEdgeCacheTests(_Yard):
    """A long-running server keeps each position's prefetched edge list (#4607).

    A journey runs in a fresh process and never holds a stale list, so this pins the
    route search to the database: a flier routes over a hard seal through an aerial
    layer built after the ground positions' edge lists were cached.
    """

    def test_flier_routes_over_a_new_aerial_layer_despite_stale_edge_caches(self) -> None:
        self.drop_detour()
        self.hard_seal()
        stale = {p.pk: list(p.all_edges_as_a) for p in (self.a, self.b, self.c)}
        materialize_aerial_layer(self.room)
        for position in (self.a, self.b, self.c):
            # What a page load's prefetch leaves behind: the edges before the layer existed.
            position.__dict__["all_edges_as_a"] = stale[position.pk]

        route = self.path(CreatureTraversal.FLIES)

        self.assertIsNotNone(route)
        self.assertIn(PositionKind.AERIAL, {p.kind for p in route})


class StrikeReachesTests(_Yard):
    """A pure function: the unplaced (None) and unknown-delivery branches no journey takes."""

    def test_strike_reaches(self) -> None:
        self.drop_detour()
        melee, missile = StrikeDelivery.MELEE, StrikeDelivery.MISSILE
        self.assertTrue(strike_reaches(self.a, self.a, melee))
        self.assertTrue(strike_reaches(self.a, self.b, melee))
        self.assertFalse(strike_reaches(self.a, self.c, melee))
        self.assertTrue(strike_reaches(self.a, self.c, missile))
        self.assertTrue(strike_reaches(None, self.c, melee))
        self.assertTrue(strike_reaches(self.a, None, melee))

    def test_unknown_delivery_is_melee(self) -> None:
        self.drop_detour()
        self.assertFalse(strike_reaches(self.a, self.c, "thrown"))


class AerialGateTests(_Yard):
    """Moving between aerial nodes once in flight; the refusal is ``HobbCannotFly``."""

    def setUp(self) -> None:
        super().setUp()
        AerialPropertyFactory()
        from evennia_extensions.factories import CharacterFactory

        self.mover = CharacterFactory(location=self.room)
        place_in_position(self.mover, self.a)
        materialize_aerial_layer(self.room)
        self.above_a = Position.objects.get(room=self.room, elevation_anchor=self.a)
        self.above_b = Position.objects.get(room=self.room, elevation_anchor=self.b)

    def test_move_between_aerial_nodes_after_taking_flight(self) -> None:
        enter_aerial(self.mover)
        move_to_position(self.mover, self.above_b)
        self.assertEqual(self.mover.object_position.position, self.above_b)


class CommitPositionTests(_Yard):
    """The cached ``current_position`` is popped on a move; journeys read ``position_of``."""

    def test_commit_position_pops_opponent_cache(self) -> None:
        encounter = CombatEncounterFactory(room=self.room)
        opponent = CombatOpponentFactory(encounter=encounter)
        place_in_position(opponent.objectdb, self.a)
        self.assertEqual(opponent.current_position, self.a)
        force_move_to_position(opponent.objectdb, self.b)
        self.assertEqual(opponent.current_position, self.b)

    def test_commit_position_pops_participant_cache(self) -> None:
        participant = CombatParticipantFactory()
        character = participant.character_sheet.character
        character.location = self.room
        character.save()
        place_in_position(character, self.a)
        self.assertEqual(participant.current_position, self.a)
        force_move_to_position(character, self.b)
        self.assertEqual(participant.current_position, self.b)
