"""NPC move plans, the advance and the target re-fit (#4607, slice 2 of #4576).

Pieces a journey cannot reach: planning idempotence, a summon advancing toward its
opponent target, and unplaced combatants staying lenient. Moving, striking and the
re-fit are journeys in ``integration_tests.test_npcs_close_in_journeys``.
The battle map is a corridor Gate - Courtyard - Keep -
Tower; every opponent here moves 1 hop a round (the NPC default).

Uses setUp (not setUpTestData): Evennia ObjectDB instances are not deepcopyable.
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.combat.constants import (
    CombatAllegiance,
    OpponentMoveKind,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import CombatOpponentAction, CombatOpponentMove
from world.combat.services.npc.npc_movement import advance_opponent, refit_targets
from world.combat.services.npc.npc_selection import ensure_opponent_plans, select_npc_actions
from world.scenes.constants import RoundStatus


class _Corridor(TestCase):
    def setUp(self) -> None:
        self.enc = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.room = self.enc.room
        self.a = PositionFactory(room=self.room, name="Gate", kind=PositionKind.PRIMARY)
        self.b = PositionFactory(room=self.room, name="Courtyard")
        self.c = PositionFactory(room=self.room, name="Keep")
        self.d = PositionFactory(room=self.room, name="Tower")
        connect_positions(self.a, self.b)
        connect_positions(self.b, self.c)
        connect_positions(self.c, self.d)

    def place_pc(self, position):
        participant = CombatParticipantFactory(encounter=self.enc)
        character = participant.character_sheet.character
        character.location = self.room
        place_in_position(character, position)
        return participant

    def opponent(self, position, **kwargs):
        opponent = CombatOpponentFactory(encounter=self.enc, **kwargs)
        place_in_position(opponent.objectdb, position)
        return opponent


class SelectionReachTests(_Corridor):
    def test_unplaced_combatants_stay_lenient(self) -> None:
        """Unit: JourneyCase always places people, so no journey has an unplaced pair."""
        pc = CombatParticipantFactory(encounter=self.enc)
        wolf = CombatOpponentFactory(encounter=self.enc)
        ThreatPoolEntryFactory(pool=wolf.threat_pool)

        actions = select_npc_actions(self.enc)

        self.assertEqual([list(a.targets.all()) for a in actions], [[pc]])
        self.assertTrue(CombatOpponentMove.objects.filter(opponent=wolf).exists())


class EnsurePlansTests(_Corridor):
    def test_idempotent_one_move_row_each(self) -> None:
        """Unit: a journey cannot call planning twice (staff and the round both can)."""
        self.place_pc(self.a)
        wolves = [self.opponent(self.c) for _ in range(2)]
        for wolf in wolves:
            ThreatPoolEntryFactory(pool=wolf.threat_pool)

        ensure_opponent_plans(self.enc)
        ensure_opponent_plans(self.enc)

        for wolf in wolves:
            self.assertEqual(CombatOpponentMove.objects.filter(opponent=wolf).count(), 1)

    def test_partial_staff_selection_plans_the_rest(self) -> None:
        """Unit: planning twice around a staff-chosen row, which a journey cannot repeat."""
        pc = self.place_pc(self.b)
        staffed = self.opponent(self.c)
        entry = ThreatPoolEntryFactory(pool=staffed.threat_pool)
        other = self.opponent(self.c)
        ThreatPoolEntryFactory(pool=other.threat_pool)
        staff_row = CombatOpponentActionFactory(
            opponent=staffed, round_number=1, threat_entry=entry
        )
        staff_row.targets.set([pc])

        ensure_opponent_plans(self.enc)
        ensure_opponent_plans(self.enc)

        self.assertEqual(CombatOpponentAction.objects.filter(opponent=staffed).count(), 1)
        self.assertEqual(CombatOpponentMove.objects.filter(opponent=staffed).count(), 1)
        self.assertEqual(CombatOpponentAction.objects.filter(opponent=other).count(), 1)
        self.assertEqual(CombatOpponentMove.objects.filter(opponent=other).count(), 1)

    def test_opponent_without_threat_pool_writes_nothing(self) -> None:
        self.place_pc(self.a)
        poolless = self.opponent(self.c, threat_pool=None)

        ensure_opponent_plans(self.enc)

        self.assertFalse(CombatOpponentMove.objects.filter(opponent=poolless).exists())


class AdvanceTests(_Corridor):
    def test_summon_advances_toward_its_opponent_target(self) -> None:
        """Unit: no journey has an ally summon."""
        # A PC stands beside the summon; it must ignore the PC and head for the enemy.
        self.place_pc(self.a)
        self.opponent(self.d, allegiance=CombatAllegiance.ENEMY)
        summon = self.opponent(self.a, allegiance=CombatAllegiance.ALLY)
        move = CombatOpponentMove.objects.create(
            opponent=summon, round_number=1, kind=OpponentMoveKind.ADVANCE
        )

        advance_opponent(summon, move, [])

        self.assertEqual(position_of(summon.objectdb), self.b)


class RefitTests(_Corridor):
    def test_unplaced_attacker_keeps_its_targets(self) -> None:
        """Unit: an unplaced attacker is not a state a journey can build."""
        pc = self.place_pc(self.a)
        wolf = CombatOpponentFactory(encounter=self.enc)
        entry = ThreatPoolEntryFactory(pool=wolf.threat_pool)
        row = CombatOpponentActionFactory(opponent=wolf, round_number=1, threat_entry=entry)
        row.targets.set([pc])

        self.assertTrue(refit_targets(row))
        self.assertEqual(list(row.targets.all()), [pc])
