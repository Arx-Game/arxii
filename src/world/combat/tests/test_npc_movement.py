"""NPC move plans, the advance and the target re-fit (#4607, slice 2 of #4576).

Pieces a journey cannot see cheaply: planning idempotence, a two-action opponent
advancing once, a summon advancing toward its opponent target, reach at selection and
the re-fit before an attack row. The battle map is a corridor Gate - Courtyard - Keep -
Tower; every opponent here moves 1 hop a round (the NPC default).

Uses setUp (not setUpTestData): Evennia ObjectDB instances are not deepcopyable.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.combat.constants import (
    ENTITY_TYPE_NPC,
    CombatAllegiance,
    OpponentMoveKind,
    StrikeDelivery,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    PendingOpponentAttackFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import CombatOpponentAction, CombatOpponentMove
from world.combat.services.npc.npc_action import _resolve_npc_action
from world.combat.services.npc.npc_movement import advance_opponent, refit_targets
from world.combat.services.npc.npc_selection import ensure_opponent_plans, select_npc_actions
from world.combat.services.rounds.action_resolution import _resolve_actions
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
    def test_out_of_reach_melee_writes_advance_only_with_goal_hint(self) -> None:
        pc = self.place_pc(self.a)
        wolf = self.opponent(self.d)
        ThreatPoolEntryFactory(pool=wolf.threat_pool, delivery=StrikeDelivery.MELEE)

        actions = select_npc_actions(self.enc)

        self.assertEqual(actions, [])
        move = CombatOpponentMove.objects.get(opponent=wolf, round_number=1)
        self.assertEqual(move.kind, OpponentMoveKind.ADVANCE)
        self.assertEqual(move.goal_position, pc.current_position)

    def test_in_reach_after_one_hop_writes_attack_and_advance(self) -> None:
        pc = self.place_pc(self.a)
        wolf = self.opponent(self.c)
        # One hop to the Courtyard puts the wolf beside the Gate.
        ThreatPoolEntryFactory(pool=wolf.threat_pool, delivery=StrikeDelivery.MELEE)

        actions = select_npc_actions(self.enc)

        self.assertEqual(len(actions), 1)
        self.assertEqual(list(actions[0].targets.all()), [pc])
        self.assertTrue(CombatOpponentMove.objects.filter(opponent=wolf).exists())

    def test_missile_reaches_across_the_room(self) -> None:
        pc = self.place_pc(self.a)
        archer = self.opponent(self.d)
        ThreatPoolEntryFactory(pool=archer.threat_pool, delivery=StrikeDelivery.MISSILE)

        actions = select_npc_actions(self.enc)

        self.assertEqual(len(actions), 1)
        self.assertEqual(list(actions[0].targets.all()), [pc])

    def test_unplaced_combatants_stay_lenient(self) -> None:
        pc = CombatParticipantFactory(encounter=self.enc)
        wolf = CombatOpponentFactory(encounter=self.enc)
        ThreatPoolEntryFactory(pool=wolf.threat_pool)

        actions = select_npc_actions(self.enc)

        self.assertEqual([list(a.targets.all()) for a in actions], [[pc]])
        self.assertTrue(CombatOpponentMove.objects.filter(opponent=wolf).exists())

    def test_all_entries_on_cooldown_still_advance(self) -> None:
        self.place_pc(self.a)
        wolf = self.opponent(self.c)
        entry = ThreatPoolEntryFactory(pool=wolf.threat_pool, cooldown_rounds=3)
        CombatOpponentActionFactory(opponent=wolf, round_number=1, threat_entry=entry)
        self.enc.round_number = 2
        self.enc.save(update_fields=["round_number"])

        select_npc_actions(self.enc)

        self.assertFalse(CombatOpponentAction.objects.filter(round_number=2).exists())
        self.assertTrue(CombatOpponentMove.objects.filter(opponent=wolf, round_number=2).exists())


class EnsurePlansTests(_Corridor):
    def test_idempotent_one_move_row_each(self) -> None:
        self.place_pc(self.a)
        wolves = [self.opponent(self.c) for _ in range(2)]
        for wolf in wolves:
            ThreatPoolEntryFactory(pool=wolf.threat_pool)

        ensure_opponent_plans(self.enc)
        ensure_opponent_plans(self.enc)

        for wolf in wolves:
            self.assertEqual(CombatOpponentMove.objects.filter(opponent=wolf).count(), 1)

    def test_partial_staff_selection_plans_the_rest(self) -> None:
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

    def test_unmatured_windup_writes_no_move(self) -> None:
        self.place_pc(self.a)
        brute = self.opponent(self.c)
        entry = ThreatPoolEntryFactory(pool=brute.threat_pool, windup_rounds=1)
        PendingOpponentAttackFactory(
            encounter=self.enc,
            opponent=brute,
            threat_entry=entry,
            declared_round=1,
            resolves_round=2,
        )

        ensure_opponent_plans(self.enc)

        self.assertFalse(CombatOpponentMove.objects.filter(opponent=brute).exists())

    def test_opponent_without_threat_pool_writes_nothing(self) -> None:
        self.place_pc(self.a)
        poolless = self.opponent(self.c, threat_pool=None)

        ensure_opponent_plans(self.enc)

        self.assertFalse(CombatOpponentMove.objects.filter(opponent=poolless).exists())


class AdvanceTests(_Corridor):
    def test_two_actions_advance_once_before_the_first_attack(self) -> None:
        pc = self.place_pc(self.a)
        ogre = self.opponent(self.d, actions_per_round=2)
        entry = ThreatPoolEntryFactory(pool=ogre.threat_pool)
        rows = []
        for _ in range(2):
            row = CombatOpponentActionFactory(opponent=ogre, round_number=1, threat_entry=entry)
            row.targets.set([pc])
            rows.append(row)
        move = CombatOpponentMove.objects.create(
            opponent=ogre, round_number=1, kind=OpponentMoveKind.ADVANCE
        )
        seen: list = []

        def record(opponent, npc_action, *args):
            seen.append(position_of(opponent.objectdb))
            return mock.MagicMock()

        with mock.patch(
            "world.combat.services.rounds.action_resolution._resolve_npc_action",
            side_effect=record,
        ):
            _resolve_actions(
                [(ENTITY_TYPE_NPC, ogre)],
                {},
                {ogre.pk: rows},
                None,
                None,
                None,
                npc_moves={ogre.pk: move},
            )

        # One hop from Tower to Keep, then both attacks from there.
        self.assertEqual(seen, [self.c, self.c])

    def test_advance_narrates_the_move(self) -> None:
        self.place_pc(self.a)
        wolf = self.opponent(self.c)
        move = CombatOpponentMove.objects.create(
            opponent=wolf, round_number=1, kind=OpponentMoveKind.ADVANCE
        )

        with mock.patch("world.combat.interaction_services.broadcast_action_outcome") as broadcast:
            final = advance_opponent(wolf, move, [])

        self.assertEqual(final, self.b)
        broadcast.assert_called_once()
        self.assertEqual(
            broadcast.call_args.kwargs["narration"], f"{wolf.name} moves to Courtyard."
        )

    def test_in_reach_does_not_move(self) -> None:
        self.place_pc(self.b)
        wolf = self.opponent(self.c)
        move = CombatOpponentMove.objects.create(
            opponent=wolf, round_number=1, kind=OpponentMoveKind.ADVANCE
        )

        self.assertIsNone(advance_opponent(wolf, move, []))
        self.assertEqual(position_of(wolf.objectdb), self.c)

    def test_summon_advances_toward_its_opponent_target(self) -> None:
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
    def test_target_out_of_reach_is_skipped_with_cannot_reach(self) -> None:
        pc = self.place_pc(self.a)
        wolf = self.opponent(self.c)
        entry = ThreatPoolEntryFactory(pool=wolf.threat_pool)
        row = CombatOpponentActionFactory(opponent=wolf, round_number=1, threat_entry=entry)
        row.targets.set([pc])

        with mock.patch("world.combat.interaction_services.broadcast_action_outcome") as broadcast:
            outcome = _resolve_npc_action(wolf, row, None, None)

        self.assertEqual(outcome.damage_results, [])
        self.assertEqual(list(row.targets.all()), [])
        broadcast.assert_called_once()
        self.assertEqual(
            broadcast.call_args.kwargs["narration"], f"{wolf.name} cannot reach anyone."
        )

    def test_single_target_lost_repicks_reachable_pc(self) -> None:
        far_pc = self.place_pc(self.a)
        near_pc = self.place_pc(self.b)
        wolf = self.opponent(self.c)
        entry = ThreatPoolEntryFactory(pool=wolf.threat_pool)
        row = CombatOpponentActionFactory(opponent=wolf, round_number=1, threat_entry=entry)
        row.targets.set([far_pc])
        row.cached_targets = [far_pc]
        row.cached_opponent_targets = []

        self.assertTrue(refit_targets(row))

        self.assertEqual(row.cached_targets, [near_pc])
        self.assertEqual(list(row.targets.all()), [near_pc])

    def test_unplaced_attacker_keeps_its_targets(self) -> None:
        pc = self.place_pc(self.a)
        wolf = CombatOpponentFactory(encounter=self.enc)
        entry = ThreatPoolEntryFactory(pool=wolf.threat_pool)
        row = CombatOpponentActionFactory(opponent=wolf, round_number=1, threat_entry=entry)
        row.targets.set([pc])

        self.assertTrue(refit_targets(row))
        self.assertEqual(list(row.targets.all()), [pc])
