"""Tests for the Monte Carlo party-vs-boss combat simulator (#1221 Task 5).

The isolation contract is the entire point of this module: a simulation run
must write nothing, fire no reactive side effects, and use only real dice
through the production combat pipeline (never ``force_check_outcome``, never
reinvented combat math).
"""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper.models import flush_cache

from world.checks.outcome_models import ConsequenceOutcome
from world.combat.constants import OpponentTier, RiskLevel
from world.combat.factories import CombatEncounterFactory, seed_scaling_defaults
from world.combat.models import CombatEncounter
from world.combat.scaling import compute_opponent_stat_block
from world.combat.simulation import SimulationParams, run_party_vs_boss_simulation
from world.scenes.models import Interaction
from world.vitals.models import CharacterVitals


class SimulationIsolationTests(TestCase):
    """The isolation contract: a simulation run persists absolutely nothing."""

    def test_simulation_writes_nothing(self) -> None:
        vitals_before = CharacterVitals.objects.count()
        encounters_before = CombatEncounter.objects.count()
        consequence_outcomes_before = ConsequenceOutcome.objects.count()
        interactions_before = Interaction.objects.count()

        run_party_vs_boss_simulation(
            SimulationParams(
                party_size=2,
                tier=OpponentTier.MOOK,
                iterations=2,
                round_cap=10,
            )
        )
        flush_cache()

        self.assertEqual(CombatEncounter.objects.count(), encounters_before)
        self.assertEqual(ConsequenceOutcome.objects.count(), consequence_outcomes_before)
        self.assertEqual(Interaction.objects.count(), interactions_before)
        self.assertEqual(CharacterVitals.objects.count(), vitals_before)


class SimulationReportShapeTests(TestCase):
    """The report's shape is internally consistent regardless of dice outcomes."""

    def test_report_shape(self) -> None:
        report = run_party_vs_boss_simulation(
            SimulationParams(
                party_size=2,
                tier=OpponentTier.MOOK,
                iterations=2,
                round_cap=10,
            )
        )

        self.assertEqual(report.iterations_run, 2)
        self.assertEqual(report.victories + report.defeats + report.stalemates, 2)
        self.assertEqual(len(report.round_counts), 2)
        self.assertGreaterEqual(report.win_rate, 0.0)
        self.assertLessEqual(report.win_rate, 1.0)


class OpponentStatBlockScalingTests(TestCase):
    """Sanity-check the scaling baseline the simulator builds its opponent from."""

    def test_party_size_scales_stat_block(self) -> None:
        seed_scaling_defaults()
        encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)

        small_party = compute_opponent_stat_block(
            OpponentTier.MOOK, encounter, party_size=2, avg_level=5
        )
        large_party = compute_opponent_stat_block(
            OpponentTier.MOOK, encounter, party_size=6, avg_level=5
        )

        self.assertGreaterEqual(large_party.max_health, small_party.max_health)
