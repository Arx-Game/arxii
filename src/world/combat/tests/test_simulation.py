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
from world.combat.models import CombatEncounter, OpponentTierTemplate
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
        self.assertGreater(report.opponent_max_health, 0)


class SimulationRespectsLiveTierTuningTests(TestCase):
    """Regression: the batch must never reset a GM's live scaling tuning.

    ``seed_scaling_defaults()`` uses ``update_or_create`` at every layer, so
    calling it unconditionally inside the batch's transaction would silently
    reset any staff tuning of ``OpponentTierTemplate`` back to the hardcoded
    defaults before the simulator's own opponent stat block is computed
    (read-your-own-writes inside the uncommitted transaction) — a
    tuning-preview tool that misrepresents the very tuning it previews.
    """

    def test_simulation_respects_live_tier_tuning(self) -> None:
        seed_scaling_defaults()
        template = OpponentTierTemplate.objects.get(tier=OpponentTier.MOOK)
        template.base_health = 7777
        template.save()

        params = SimulationParams(
            party_size=2,
            avg_level=5,
            tier=OpponentTier.MOOK,
            risk_level=RiskLevel.MODERATE,
            iterations=1,
            round_cap=5,
        )

        report = run_party_vs_boss_simulation(params)

        # Compute the expected scaled value the same way the simulator does —
        # never hand-derived — using a throwaway encounter with identical
        # party/risk context, against the tuning that's live right now.
        throwaway_encounter = CombatEncounterFactory(risk_level=params.risk_level)
        expected_block = compute_opponent_stat_block(
            params.tier,
            throwaway_encounter,
            party_size=params.party_size,
            avg_level=float(params.avg_level),
        )

        self.assertEqual(report.opponent_max_health, expected_block.max_health)

        # Sanity check the regression actually bites: the hardcoded MOOK
        # default (base_health=30) scaled by the same party/risk context caps
        # out under 100, while the 7777 tuning scales into the thousands.
        # Pre-fix, the batch's unconditional seed_scaling_defaults() call
        # would have reset base_health back to 30 inside the batch's
        # transaction before the opponent stat block was computed, so
        # report.opponent_max_health would have landed under 100 instead.
        self.assertGreater(report.opponent_max_health, 1000)


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
