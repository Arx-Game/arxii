"""Tests for the generic debt/petition-streak service primitives (#1718)."""

from django.test import TestCase

from world.npc_services.factories import NPCStandingFactory
from world.npc_services.services import (
    incur_npc_debt,
    outstanding_debt,
    record_petition_outcome,
)


class IncurNpcDebtTests(TestCase):
    def test_increments_debt_and_stamps_baseline(self):
        standing = NPCStandingFactory(affection=40)
        result = incur_npc_debt(standing, 5, current_affection=40, current_missions_completed=2)
        self.assertEqual(result.debt, 5)
        self.assertEqual(result.debt_baseline_affection, 40)
        self.assertEqual(result.debt_baseline_missions_completed, 2)

    def test_accumulates_across_calls(self):
        standing = NPCStandingFactory(affection=10)
        incur_npc_debt(standing, 3, current_affection=10, current_missions_completed=0)
        standing.refresh_from_db()
        result = incur_npc_debt(standing, 4, current_affection=15, current_missions_completed=1)
        self.assertEqual(result.debt, 7)
        self.assertEqual(result.debt_baseline_affection, 15)
        self.assertEqual(result.debt_baseline_missions_completed, 1)


class OutstandingDebtTests(TestCase):
    def test_zero_debt_is_zero(self):
        standing = NPCStandingFactory()
        self.assertEqual(
            outstanding_debt(
                standing,
                current_affection=0,
                current_missions_completed=0,
                affection_divisor=10,
                mission_divisor=2,
            ),
            0,
        )

    def test_nets_against_affection_gain_since_baseline(self):
        standing = NPCStandingFactory(
            debt=5, debt_baseline_affection=10, debt_baseline_missions_completed=0
        )
        # +20 affection since baseline, divisor 10 -> 2 repaid.
        result = outstanding_debt(
            standing,
            current_affection=30,
            current_missions_completed=0,
            affection_divisor=10,
            mission_divisor=2,
        )
        self.assertEqual(result, 3)

    def test_nets_against_missions_completed_since_baseline(self):
        standing = NPCStandingFactory(
            debt=5, debt_baseline_affection=0, debt_baseline_missions_completed=1
        )
        # +4 missions since baseline, divisor 2 -> 2 repaid.
        result = outstanding_debt(
            standing,
            current_affection=0,
            current_missions_completed=5,
            affection_divisor=10,
            mission_divisor=2,
        )
        self.assertEqual(result, 3)

    def test_never_goes_below_zero(self):
        standing = NPCStandingFactory(
            debt=2, debt_baseline_affection=0, debt_baseline_missions_completed=0
        )
        result = outstanding_debt(
            standing,
            current_affection=1000,
            current_missions_completed=1000,
            affection_divisor=10,
            mission_divisor=2,
        )
        self.assertEqual(result, 0)


class RecordPetitionOutcomeTests(TestCase):
    def test_success_resets_streak(self):
        standing = NPCStandingFactory(consecutive_failed_petitions=2)
        crossed = record_petition_outcome(standing, succeeded=True, escalation_threshold=3)
        standing.refresh_from_db()
        self.assertFalse(crossed)
        self.assertEqual(standing.consecutive_failed_petitions, 0)

    def test_failure_increments_streak(self):
        standing = NPCStandingFactory(consecutive_failed_petitions=1)
        crossed = record_petition_outcome(standing, succeeded=False, escalation_threshold=3)
        standing.refresh_from_db()
        self.assertFalse(crossed)
        self.assertEqual(standing.consecutive_failed_petitions, 2)

    def test_failure_crossing_threshold_reports_true(self):
        standing = NPCStandingFactory(consecutive_failed_petitions=2)
        crossed = record_petition_outcome(standing, succeeded=False, escalation_threshold=3)
        standing.refresh_from_db()
        self.assertTrue(crossed)
        self.assertEqual(standing.consecutive_failed_petitions, 3)
