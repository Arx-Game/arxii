"""Schema rules for NPC movement plans and creature movement profiles (#4607)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.areas.positioning.factories import PositionEdgeFactory
from world.combat.constants import (
    OpponentMoveKind,
)
from world.combat.factories import (
    CombatOpponentFactory,
    CombatOpponentMoveFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import CombatOpponentMove


class CombatOpponentMoveConstraintTests(TestCase):
    """Database constraints on BASH and WAIT rows, which later slices write.

    No journey reaches a BASH or WAIT row yet (slice 2 only writes ADVANCE), so these stay
    units until the slices that write them land journeys of their own.
    """

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

    def test_wait_requires_threat_entry(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CombatOpponentMove.objects.create(
                opponent=self.opponent,
                round_number=1,
                kind=OpponentMoveKind.WAIT,
            )

    def test_one_move_per_opponent_per_round(self):
        CombatOpponentMoveFactory(opponent=self.opponent, round_number=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CombatOpponentMoveFactory(opponent=self.opponent, round_number=2)
