"""Fuzz: no enemy idles through a round it could act in (#4609, the progress guarantee).

Hypothesis builds a random connected room of 3 to 6 positions. Every edge is open, a
conjured wall with a strength (sometimes with a climb past it), or a staff-built wall
nothing can break. One or two player characters stand somewhere on it, and one to three
enemies elsewhere, each with a random tactics level, 1 or 2 hops, walking or climbing, a
bite and sometimes a bow. One round resolves through ``resolve_round``.

The property is judged on what happened, never on what selection wrote: each enemy
either resolved an attack, stood somewhere else afterwards, battered a wall (its strength
dropped or the wall came down), held a waiting strike, or left the fight.

The only enemies excused are the physically stuck, judged from the drawn edges alone: a
mindless one (it never waits) with no bow, from which no position beside a player can be
reached over anything but walls nothing can break. A cunning or tactical one in that spot
still waits for an opening, so it is never excused in a first round.
"""

from __future__ import annotations

from collections import deque
from unittest.mock import MagicMock

from evennia import create_object
from hypothesis import given, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from evennia_extensions.factories import CharacterFactory
from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.models import PositionEdge
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    create_position,
    place_in_position,
    position_of,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ENTITY_TYPE_NPC,
    CreatureTactics,
    OpponentMoveKind,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentMove
from world.combat.services import resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.mechanics.factories import ChallengeInstanceFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

OPEN, WALL, GATED_WALL, SEAL = "open", "wall", "gated_wall", "seal"
edge_states = st.sampled_from([OPEN, OPEN, WALL, GATED_WALL, SEAL])

enemies = st.tuples(
    st.sampled_from(CreatureTactics.values),
    st.integers(min_value=1, max_value=2),  # hops
    st.sampled_from([CreatureTraversal.WALKS, CreatureTraversal.CLIMBS]),
    st.booleans(),  # carries a bow
)


@st.composite
def fields(draw: st.DrawFn) -> dict:
    """A room, its edges with their states and strengths, and who stands where."""
    count = draw(st.integers(min_value=3, max_value=6))
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
    edges = [
        (a, b, draw(edge_states), draw(st.integers(min_value=1, max_value=30)))
        for a, b in sorted(pairs)
    ]
    spots = st.integers(0, count - 1)
    return {
        "count": count,
        "edges": edges,
        "players": draw(st.lists(spots, min_size=1, max_size=2)),
        "enemies": draw(st.lists(st.tuples(spots, enemies), min_size=1, max_size=3)),
    }


def _full_strength(*args: object, **kwargs: object) -> MagicMock:
    return MagicMock(success_level=0)


def stuck(field: dict, start: int, tactics: str, bow: bool) -> bool:
    """The physically stuck enemy, from the drawn edges alone (see the module docstring)."""
    if bow or tactics != CreatureTactics.MINDLESS:
        return False
    beside_a_player = set(field["players"])
    for a, b, state, _strength in field["edges"]:
        if state == OPEN:
            if a in field["players"]:
                beside_a_player.add(b)
            if b in field["players"]:
                beside_a_player.add(a)
    neighbours: dict[int, set[int]] = {i: set() for i in range(field["count"])}
    for a, b, state, _strength in field["edges"]:
        if state != SEAL:
            neighbours[a].add(b)
            neighbours[b].add(a)
    seen, frontier = {start}, deque([start])
    while frontier:
        here = frontier.popleft()
        for there in neighbours[here] - seen:
            seen.add(there)
            frontier.append(there)
    return not (seen & beside_a_player)


class NoEnemyIdles(HypothesisTestCase):
    def build(self, field: dict):
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=60, base_soak=0)
        room = create_object("typeclasses.rooms.Room", key="Fuzz Field", nohome=True)
        positions = [
            create_position(room, f"P{i}", kind=PositionKind.FEATURE) for i in range(field["count"])
        ]
        gate = ChallengeInstanceFactory(location=room, target_object=room)
        for a, b, state, strength in field["edges"]:
            here, there = positions[a], positions[b]
            if state == OPEN:
                connect_positions(here, there)
            elif state == SEAL:
                connect_positions(here, there, is_passable=False)
            else:
                create_conjured_obstacle(
                    here,
                    there,
                    caster_sheet=None,
                    integrity=strength,
                    gating_challenge=gate if state == GATED_WALL else None,
                )
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1, room=room)
        for index, spot in enumerate(field["players"]):
            character = CharacterFactory(db_key=f"Player{index}", location=room)
            sheet = CharacterSheetFactory(character=character)
            CharacterVitals.objects.create(
                character_sheet=sheet, health=100, max_health=100, base_max_health=100
            )
            CombatParticipantFactory(
                encounter=encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
            )
            place_in_position(character, positions[spot])
        opponents = []
        for index, (spot, (tactics, hops, traversal, bow)) in enumerate(field["enemies"]):
            pool = ThreatPoolFactory(name=f"Enemy{index} attacks")
            ThreatPoolEntryFactory(
                pool=pool,
                name=f"Enemy{index} bite",
                base_damage=5,
                delivery=StrikeDelivery.MELEE,
                targeting_mode=TargetingMode.SINGLE,
                target_selection=TargetSelection.RANDOM,
            )
            if bow:
                ThreatPoolEntryFactory(
                    pool=pool,
                    name=f"Enemy{index} arrow",
                    base_damage=5,
                    delivery=StrikeDelivery.MISSILE,
                    targeting_mode=TargetingMode.SINGLE,
                    target_selection=TargetSelection.RANDOM,
                )
            template = CreatureTemplateFactory(
                name=f"Enemy{index}",
                tier=OpponentTier.MOOK,
                threat_pool=pool,
                tactics=tactics,
                speed_hops=hops,
                traversal=traversal,
            )
            opponents.append(
                spawn_from_creature_template(encounter, template, position=positions[spot])
            )
        return encounter, opponents

    @given(fields())
    def test_every_enemy_that_can_act_does_something_you_can_see(self, field: dict) -> None:
        encounter, opponents = self.build(field)
        before = {o.pk: position_of(o.objectdb) for o in opponents}
        walls = {
            e.pk: (e.is_passable, e.integrity)
            for e in PositionEdge.objects.filter(position_a__room_id=encounter.room_id)
        }

        result = resolve_round(encounter, defense_check_fn=_full_strength)

        for opponent, (spot, (tactics, _hops, _traversal, bow)) in zip(
            opponents, field["enemies"], strict=True
        ):
            if stuck(field, spot, tactics, bow):
                continue
            opponent.refresh_from_db()
            plan = CombatOpponentMove.objects.filter(opponent=opponent, round_number=1).first()
            attacked = any(
                o.entity_type == ENTITY_TYPE_NPC
                and o.entity_label == str(opponent)
                and o.damage_results
                for o in result.action_outcomes
            )
            moved = (
                opponent.objectdb is not None
                and position_of(opponent.objectdb) != before[opponent.pk]
            )
            bashed = False
            if plan is not None and plan.kind == OpponentMoveKind.BASH:
                wall = PositionEdge.objects.get(pk=plan.barrier_edge_id)
                bashed = (wall.is_passable, wall.integrity) != walls[wall.pk]
            waited = plan is not None and plan.kind == OpponentMoveKind.WAIT
            fled = opponent.status == OpponentStatus.FLED
            self.assertTrue(
                attacked or moved or bashed or waited or fled,
                f"{opponent.name} ({tactics}) idled. Plan: "
                f"{plan.kind if plan is not None else None}. Field: {field}",
            )
