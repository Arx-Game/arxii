"""Tests for accrue_corruption_for_cast orchestrator (Scope #7, Task 2).

Formula (spec §3.1):
    involvement = stat_bonus_contribution + thread_pull_resonance_spent
    base_tick   = involvement × affinity_coef/10 × tier_coef/10
    multipliers = (deficit_mul × mishap_mul × audere_mul) / 1000
    tick        = ceil(base_tick × multipliers)

Default config coefficients (integer-tenths):
    celestial = 0, primal = 2, abyssal = 10
    tier 1 = 10, tier 2 = 20, tier 3 = 40, tier 4 = 80, tier 5 = 160
    deficit_multiplier = 20, mishap_multiplier = 15, audere_multiplier = 15
"""

from unittest import mock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.types import AdvancementOutcome
from world.magic.factories import AffinityFactory, ResonanceFactory, TechniqueFactory
from world.magic.models.corruption_config import CorruptionConfig
from world.magic.services.corruption import accrue_corruption_for_cast
from world.magic.types.corruption import (
    CorruptionAccrualResult,
    CorruptionAccrualSummary,
    CorruptionSource,
)
from world.magic.types.techniques import AnimaCostResult, ResonanceInvolvement, TechniqueUseResult


def _make_anima_cost() -> AnimaCostResult:
    """Minimal AnimaCostResult for constructing TechniqueUseResult."""
    return AnimaCostResult(
        base_cost=2,
        effective_cost=2,
        control_delta=0,
        current_anima=10,
        deficit=0,
    )


def _make_result(
    *,
    technique,
    resonance_involvements=(),
    was_deficit=False,
    was_mishap=False,
    was_audere=False,
) -> TechniqueUseResult:
    """Build a minimal TechniqueUseResult for testing."""
    return TechniqueUseResult(
        anima_cost=_make_anima_cost(),
        technique=technique,
        was_deficit=was_deficit,
        was_mishap=was_mishap,
        was_audere=was_audere,
        resonance_involvements=tuple(resonance_involvements),
    )


def _make_corruption_template(resonance):
    """Create a minimal Corruption ConditionTemplate wired to a resonance."""
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name})",
        has_progression=True,
        corruption_resonance=resonance,
    )
    thresholds = [50, 200, 500, 1000, 1500]
    for i, threshold in enumerate(thresholds, start=1):
        ConditionStageFactory(
            condition=template,
            stage_order=i,
            severity_threshold=threshold,
        )
    return template


class TestAccrueCorruptionForCast(TestCase):
    """accrue_corruption_for_cast per-resonance dispatch and formula."""

    def _call(self, caster_sheet=None, **kwargs) -> CorruptionAccrualSummary:
        sheet = caster_sheet or CharacterSheetFactory()
        return accrue_corruption_for_cast(caster_sheet=sheet, **kwargs)

    # ------------------------------------------------------------------
    # Celestial skip
    # ------------------------------------------------------------------

    def test_celestial_resonance_zero_tick(self) -> None:
        """Celestial resonance skipped entirely — no accrue_corruption call, empty per_resonance."""
        celestial_affinity = AffinityFactory(name="Celestial")
        celestial_resonance = ResonanceFactory(name="Celestial Test", affinity=celestial_affinity)
        technique = TechniqueFactory(level=1)  # tier 1
        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=celestial_resonance,
                    stat_bonus_contribution=10,
                    thread_pull_resonance_spent=5,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            summary = self._call(technique_use_result=result_obj)

        mock_accrue.assert_not_called()
        self.assertIsInstance(summary, CorruptionAccrualSummary)
        self.assertEqual(summary.per_resonance, ())

    # ------------------------------------------------------------------
    # Abyssal baseline
    # ------------------------------------------------------------------

    def test_abyssal_tier_1_cantrip_stat_bonus_2_yields_2_ticks(self) -> None:
        """Abyssal, tier 1, stat_bonus=2, no flags → tick = ceil(2 × 1.0 × 1.0 × 1.0) = 2."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Test", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        mock_accrue.assert_called_once()
        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 2)
        self.assertEqual(call_kwargs["resonance"], resonance)

    # ------------------------------------------------------------------
    # Multiplier tests
    # ------------------------------------------------------------------

    def test_audere_multiplier_applied(self) -> None:
        """was_audere=True → 1.5× multiplier; ceil(2 × 1.0 × 1.0 × 1.5) = 3."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Audere", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
            was_audere=True,
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 3)

    def test_deficit_multiplier_applied(self) -> None:
        """was_deficit=True → 2× multiplier; ceil(2 × 1.0 × 1.0 × 2.0) = 4."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Deficit", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
            was_deficit=True,
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 4)

    def test_mishap_multiplier_applied(self) -> None:
        """was_mishap=True → 1.5× multiplier; ceil(2 × 1.0 × 1.0 × 1.5) = 3."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Mishap", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
            was_mishap=True,
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 3)

    def test_combined_multipliers_compound(self) -> None:
        """All three flags True → multiplier = 2.0 × 1.5 × 1.5 = 4.5; tick = ceil(2 × 4.5) = 9."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal All Flags", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
            was_deficit=True,
            was_mishap=True,
            was_audere=True,
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 9)

    # ------------------------------------------------------------------
    # involvement from thread pulls
    # ------------------------------------------------------------------

    def test_thread_pull_resonance_spent_adds_to_involvement(self) -> None:
        """stat_bonus=2, thread_pull=3 → involvement=5; tick = ceil(5 × 1.0 × 1.0 × 1.0) = 5."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Thread", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=3,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 5)

    # ------------------------------------------------------------------
    # Multi-resonance
    # ------------------------------------------------------------------

    def test_multi_resonance_distributes_per_resonance_ticks(self) -> None:
        """Two non-zero involvements → two accrue_corruption calls with distinct resonances.

        Primal coef=2 (×0.1→0.2), Abyssal coef=10 (×0.1→1.0), tier 1 coef=10 (×0.1→1.0).
        Primal involvement=10: base = 10 × 0.2 × 1.0 = 2.0 → ceil(2.0) = 2
        Abyssal involvement=10: base = 10 × 1.0 × 1.0 = 10.0 → ceil(10.0) = 10
        """
        primal_affinity = AffinityFactory(name="Primal")
        abyssal_affinity = AffinityFactory(name="Abyssal")
        primal_resonance = ResonanceFactory(name="Primal Multi", affinity=primal_affinity)
        abyssal_resonance = ResonanceFactory(name="Abyssal Multi", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=primal_resonance,
                    stat_bonus_contribution=10,
                    thread_pull_resonance_spent=0,
                ),
                ResonanceInvolvement(
                    resonance=abyssal_resonance,
                    stat_bonus_contribution=10,
                    thread_pull_resonance_spent=0,
                ),
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            summary = self._call(technique_use_result=result_obj)

        self.assertEqual(mock_accrue.call_count, 2)
        amounts = {
            call.kwargs["resonance"]: call.kwargs["amount"] for call in mock_accrue.call_args_list
        }
        self.assertEqual(amounts[primal_resonance], 2)
        self.assertEqual(amounts[abyssal_resonance], 10)
        # Both results are in per_resonance
        self.assertEqual(len(summary.per_resonance), 2)

    # ------------------------------------------------------------------
    # Zero involvement / zero tick skip
    # ------------------------------------------------------------------

    def test_zero_involvement_skips_call(self) -> None:
        """involvement = 0 → no accrue_corruption call."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Zero", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=0,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            summary = self._call(technique_use_result=result_obj)

        mock_accrue.assert_not_called()
        self.assertEqual(summary.per_resonance, ())

    # ------------------------------------------------------------------
    # Tier coefficient
    # ------------------------------------------------------------------

    def test_tier_3_coefficient_quadruples_baseline(self) -> None:
        """technique.tier=3 → tier_coef=40 (4× tier 1); Abyssal, stat_bonus=2, no flags.

        base = 2 × (10/10) × (40/10) = 2 × 1.0 × 4.0 = 8.0 → tick = ceil(8.0) = 8.
        """
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Tier3", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=11)  # level 11 → tier 3

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 8)

    # ------------------------------------------------------------------
    # Return type and structure
    # ------------------------------------------------------------------

    def test_returns_corruption_accrual_summary(self) -> None:
        """Return value is a CorruptionAccrualSummary with correct fields populated."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Summary", affinity=abyssal_affinity)
        sheet = CharacterSheetFactory()
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            summary = self._call(caster_sheet=sheet, technique_use_result=result_obj)

        self.assertIsInstance(summary, CorruptionAccrualSummary)
        self.assertEqual(summary.caster_sheet_id, sheet.pk)
        self.assertEqual(summary.technique_id, technique.pk)
        self.assertEqual(len(summary.per_resonance), 1)

    def test_per_resonance_tuple_contains_accrual_results(self) -> None:
        """Each per_resonance entry is the CorruptionAccrualResult returned by accrue_corruption."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Result", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        fake_accrual_result = CorruptionAccrualResult(
            resonance=resonance,
            amount_applied=2,
            current_before=0,
            current_after=2,
            lifetime_before=0,
            lifetime_after=2,
            stage_before=0,
            stage_after=0,
            advancement_outcome=AdvancementOutcome.NO_CHANGE,
            condition_instance=None,
        )

        with mock.patch(
            "world.magic.services.corruption.accrue_corruption",
            return_value=fake_accrual_result,
        ):
            summary = self._call(technique_use_result=result_obj)

        self.assertEqual(len(summary.per_resonance), 1)
        self.assertIs(summary.per_resonance[0], fake_accrual_result)

    # ------------------------------------------------------------------
    # No template authored — still calls accrue_corruption (real integration)
    # ------------------------------------------------------------------

    def test_no_template_authored_still_returns_summary(self) -> None:
        """Resonance with no ConditionTemplate → accrue_corruption is still called.

        accrue_corruption returns a no-op CorruptionAccrualResult; the result
        is added to per_resonance. corruption_current still increments.
        """
        from world.magic.models.aura import CharacterResonance

        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal NoTemplate", affinity=abyssal_affinity)
        sheet = CharacterSheetFactory()
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        # No template created — accrue_corruption fires but is a no-op for conditions
        summary = accrue_corruption_for_cast(
            caster_sheet=sheet,
            technique_use_result=result_obj,
        )

        self.assertIsInstance(summary, CorruptionAccrualSummary)
        self.assertEqual(len(summary.per_resonance), 1)
        # Field still incremented
        row = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(row.corruption_current, 2)

    # ------------------------------------------------------------------
    # Explicit config override
    # ------------------------------------------------------------------

    def test_explicit_config_override_zeros_all_ticks(self) -> None:
        """Config with all affinity coefs=0 produces zero ticks and empty per_resonance tuple."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal Zeroed", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=10,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        # All affinity coefficients zeroed out — unsaved, used as config override
        zero_config = CorruptionConfig(
            celestial_coefficient=0,
            primal_coefficient=0,
            abyssal_coefficient=0,
            tier_1_coefficient=10,
            tier_2_coefficient=20,
            tier_3_coefficient=40,
            tier_4_coefficient=80,
            tier_5_coefficient=160,
            deficit_multiplier=20,
            mishap_multiplier=15,
            audere_multiplier=15,
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            summary = self._call(
                technique_use_result=result_obj,
                config=zero_config,
            )

        mock_accrue.assert_not_called()
        self.assertEqual(summary.per_resonance, ())

    # ------------------------------------------------------------------
    # Primal coefficient
    # ------------------------------------------------------------------

    def test_primal_coefficient_applied(self) -> None:
        """Primal coef=2, tier 1, involvement=10 → base = 10 × 0.2 × 1.0 = 2.0 → tick=2."""
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(name="Primal Coef", affinity=primal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=10,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 2)

    def test_primal_low_involvement_rounds_up_to_one(self) -> None:
        """Primal coef=2, tier 1, involvement=1 → base = 1 × 0.2 × 1.0 = 0.2 → ceil(0.2) = 1."""
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(name="Primal Ceil", affinity=primal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=1,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertEqual(call_kwargs["amount"], 1)

    # ------------------------------------------------------------------
    # accrue_corruption receives correct keyword args
    # ------------------------------------------------------------------

    def test_accrue_corruption_receives_technique_use_kwarg(self) -> None:
        """accrue_corruption is called with technique_use=technique_use_result for audit trail."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(name="Abyssal AuditArg", affinity=abyssal_affinity)
        technique = TechniqueFactory(level=1)

        result_obj = _make_result(
            technique=technique,
            resonance_involvements=[
                ResonanceInvolvement(
                    resonance=resonance,
                    stat_bonus_contribution=2,
                    thread_pull_resonance_spent=0,
                )
            ],
        )

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            mock_accrue.return_value = mock.MagicMock()
            self._call(technique_use_result=result_obj)

        call_kwargs = mock_accrue.call_args.kwargs
        self.assertIs(call_kwargs["technique_use"], result_obj)
        self.assertEqual(call_kwargs["source"], CorruptionSource.TECHNIQUE_USE)

    # ------------------------------------------------------------------
    # Empty resonance_involvements
    # ------------------------------------------------------------------

    def test_empty_involvements_returns_empty_summary(self) -> None:
        """No involvements → no accrue_corruption calls, empty per_resonance."""
        sheet = CharacterSheetFactory()
        technique = TechniqueFactory(level=1)
        result_obj = _make_result(technique=technique, resonance_involvements=[])

        with mock.patch("world.magic.services.corruption.accrue_corruption") as mock_accrue:
            summary = accrue_corruption_for_cast(
                caster_sheet=sheet,
                technique_use_result=result_obj,
            )

        mock_accrue.assert_not_called()
        self.assertIsInstance(summary, CorruptionAccrualSummary)
        self.assertEqual(summary.per_resonance, ())
        self.assertEqual(summary.technique_id, technique.pk)
