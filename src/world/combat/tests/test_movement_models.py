"""Schema rules for NPC movement plans and creature movement profiles (#4607)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.factories import PositionEdgeFactory
from world.combat.constants import (
    NPC_DEFAULT_HOPS,
    NPC_DEFAULT_TACTICS,
    NPC_DEFAULT_TRAVERSAL,
    CreatureTactics,
    OpponentMoveKind,
)
from world.combat.factories import (
    CombatOpponentFactory,
    CombatOpponentMoveFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import CombatOpponentMove
from world.combat.types import MovementProfile


class CombatOpponentMoveConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.opponent = CombatOpponentFactory()
        cls.entry = ThreatPoolEntryFactory()
        cls.edge = PositionEdgeFactory()

    def test_bash_requires_barrier_edge(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CombatOpponentMove.objects.create(
                opponent=self.opponent,
                round_number=1,
                kind=OpponentMoveKind.BASH,
                threat_entry=self.entry,
            )

    def test_bash_requires_threat_entry(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CombatOpponentMove.objects.create(
                opponent=self.opponent,
                round_number=1,
                kind=OpponentMoveKind.BASH,
                barrier_edge=self.edge,
            )

    def test_bash_with_edge_and_entry_saves(self):
        move = CombatOpponentMove.objects.create(
            opponent=self.opponent,
            round_number=1,
            kind=OpponentMoveKind.BASH,
            barrier_edge=self.edge,
            threat_entry=self.entry,
        )
        self.assertFalse(move.fired)

    def test_wait_requires_threat_entry(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CombatOpponentMove.objects.create(
                opponent=self.opponent,
                round_number=1,
                kind=OpponentMoveKind.WAIT,
            )

    def test_advance_needs_nothing_else(self):
        move = CombatOpponentMove.objects.create(
            opponent=self.opponent,
            round_number=1,
            kind=OpponentMoveKind.ADVANCE,
        )
        self.assertIsNone(move.goal_position)
        self.assertIn(self.opponent.name, str(move))

    def test_one_move_per_opponent_per_round(self):
        CombatOpponentMoveFactory(opponent=self.opponent, round_number=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CombatOpponentMoveFactory(opponent=self.opponent, round_number=2)


class MovementProfileTests(TestCase):
    def test_template_less_opponent_uses_npc_defaults(self):
        opponent = CombatOpponentFactory(creature_template=None)
        self.assertEqual(
            opponent.movement_profile,
            MovementProfile(
                tactics=NPC_DEFAULT_TACTICS,
                speed_hops=NPC_DEFAULT_HOPS,
                traversal=NPC_DEFAULT_TRAVERSAL,
            ),
        )

    def test_new_template_defaults_match_npc_defaults(self):
        template = CreatureTemplateFactory()
        self.assertEqual(template.tactics, NPC_DEFAULT_TACTICS)
        self.assertEqual(template.speed_hops, NPC_DEFAULT_HOPS)
        self.assertEqual(template.traversal, NPC_DEFAULT_TRAVERSAL)

    def test_opponent_reads_its_template(self):
        template = CreatureTemplateFactory(
            tactics=CreatureTactics.MINDLESS,
            speed_hops=3,
            traversal=CreatureTraversal.FLIES,
        )
        opponent = CombatOpponentFactory(creature_template=template)
        self.assertEqual(
            opponent.movement_profile,
            MovementProfile(
                tactics=CreatureTactics.MINDLESS,
                speed_hops=3,
                traversal=CreatureTraversal.FLIES,
            ),
        )

    def test_participant_hops_used_starts_at_zero(self):
        self.assertEqual(CombatParticipantFactory().hops_used, 0)
