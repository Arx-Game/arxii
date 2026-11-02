"""Tests for the Monte Carlo party-vs-boss combat simulator (#1221 Task 5).

The isolation contract is the entire point of this module: a simulation run
must write nothing, fire no reactive side effects, and use only real dice
through the production combat pipeline (never ``force_check_outcome``, never
reinvented combat math).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.utils.idmapper.models import flush_cache

from actions.factories import ActionTemplateFactory
from world.checks.outcome_models import ConsequenceOutcome
from world.combat import services
from world.combat.constants import OpponentTier, RiskLevel
from world.combat.factories import CombatEncounterFactory, seed_scaling_defaults
from world.combat.models import (
    CombatEncounter,
    CombatParticipant,
    CombatRoundAction,
    OpponentTierTemplate,
)
from world.combat.scaling import compute_opponent_stat_block
from world.combat.simulation import SimulationParams, run_party_vs_boss_simulation
from world.covenants.factories import CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.magic.constants import TargetKind
from world.magic.factories import TechniqueFactory
from world.magic.models import Thread
from world.magic.services.threads import shown_thread_level
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


class SimulationComboRateTests(TestCase):
    """Tests for the combo_rate simulation parameter."""

    def test_combo_rate_zero_default(self) -> None:
        params = SimulationParams()
        self.assertEqual(params.combo_rate, 0.0)

    def test_combo_rate_one(self) -> None:
        params = SimulationParams(combo_rate=1.0)
        self.assertEqual(params.combo_rate, 1.0)

    def test_simulation_runs_with_combo_rate(self) -> None:
        """A simulation with combo_rate > 0 should complete without errors."""
        seed_scaling_defaults()
        report = run_party_vs_boss_simulation(
            SimulationParams(
                party_size=2,
                tier=OpponentTier.MOOK,
                iterations=1,
                round_cap=5,
                combo_rate=0.5,
            )
        )
        self.assertEqual(report.iterations_run, 1)


class SimulationTechniqueAndVowTests(TestCase):
    """The party's technique and vow (#4930), seen from inside each round.

    ``resolve_round`` is wrapped, not replaced: the wrapper reads the round's
    declarations and the party's vows, then the real round resolves. Every row it
    sees rolls back with the batch.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(
            name="Simulated lash", action_template=ActionTemplateFactory()
        )
        cls.role = CovenantRoleFactory(name="Simulated vow")

    def _run(self, **params: object) -> list[CombatEncounter]:
        seen: list[CombatEncounter] = []
        self.actions: set[int] = set()
        self.memberships: list[tuple[int, int, int | None]] = []
        real = services.resolve_round

        def watch(encounter: CombatEncounter) -> None:
            seen.append(encounter)
            self.actions |= set(
                CombatRoundAction.objects.filter(participant__encounter=encounter).values_list(
                    "focused_action_id", flat=True
                )
            )
            for participant in CombatParticipant.objects.filter(encounter=encounter):
                sheet = participant.character_sheet
                membership = CharacterCovenantRole.objects.filter(
                    character_sheet=sheet, left_at__isnull=True
                ).first()
                thread = Thread.objects.filter(
                    owner=sheet, target_kind=TargetKind.COVENANT_ROLE
                ).first()
                self.memberships.append(
                    (
                        sheet.pk,
                        membership.covenant_role_id if membership else 0,
                        shown_thread_level(thread.level) if thread else None,
                    )
                )
            real(encounter)

        with patch.object(services, "resolve_round", side_effect=watch):
            run_party_vs_boss_simulation(
                SimulationParams(
                    party_size=2,
                    avg_level=4,
                    tier=OpponentTier.MOOK,
                    iterations=1,
                    round_cap=1,
                    **params,
                )
            )
        return seen

    def test_a_technique_is_what_every_party_member_casts(self) -> None:
        self.assertTrue(self._run(technique_id=self.technique.pk))
        self.assertEqual(self.actions, {self.technique.pk})

    def test_without_one_the_party_casts_the_basic_attack(self) -> None:
        self._run()
        self.assertEqual(len(self.actions), 1)
        self.assertNotIn(self.technique.pk, self.actions)

    def test_a_vow_gives_every_member_the_membership_and_its_thread(self) -> None:
        self._run(covenant_role_id=self.role.pk)
        self.assertEqual(len(self.memberships), 2)
        for _sheet, role_id, level in self.memberships:
            self.assertEqual((role_id, level), (self.role.pk, 4))

    def test_without_one_nobody_holds_a_vow(self) -> None:
        self._run()
        self.assertEqual([(r, lvl) for _s, r, lvl in self.memberships], [(0, None)] * 2)

    def test_the_run_still_writes_nothing(self) -> None:
        before = CharacterCovenantRole.objects.count()
        self._run(technique_id=self.technique.pk, covenant_role_id=self.role.pk)
        flush_cache()
        self.assertEqual(CharacterCovenantRole.objects.count(), before)
        self.assertEqual(CombatEncounter.objects.count(), 0)
