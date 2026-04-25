"""Tests for the Atonement Rite service (Scope #7 Phase 8)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    AffinityFactory,
    AtonementRitualFactory,
    ResonanceFactory,
    with_corruption_at_stage,
)
from world.magic.models import CharacterAffinityTotal
from world.magic.services.atonement import (
    ATONEMENT_REDUCE_AMOUNT,
    AtonementAffinityRefused,
    AtonementResult,
    AtonementSelfTargetRequired,
    AtonementStageOutOfRange,
    perform_atonement_rite,
)


def _call(*, performer_sheet, target_sheet, resonance):
    return perform_atonement_rite(
        performer_sheet=performer_sheet,
        target_sheet=target_sheet,
        resonance=resonance,
    )


def _set_dominant_affinity(sheet, affinity_name: str) -> None:
    """Wire a CharacterAffinityTotal row so dominant affinity resolves correctly."""
    affinity = AffinityFactory(name=affinity_name)
    CharacterAffinityTotal.objects.update_or_create(
        character=sheet,
        affinity=affinity,
        defaults={"total": 100},
    )
    # Make other affinities lower so this one dominates
    for name in {"Celestial", "Primal", "Abyssal"} - {affinity_name}:
        other = AffinityFactory(name=name)
        CharacterAffinityTotal.objects.update_or_create(
            character=sheet,
            affinity=other,
            defaults={"total": 1},
        )


class TestAtonementRiteHappyPath(TestCase):
    """Celestial / Primal performers at stages 1-2 succeed."""

    def test_celestial_self_target_stage_2_reduces(self) -> None:
        """Celestial-dominant performer; stage-2 Primal resonance corruption."""
        sheet = CharacterSheetFactory()
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=primal_affinity)
        _set_dominant_affinity(sheet, "Celestial")
        with_corruption_at_stage(sheet, resonance, stage=2)

        result = _call(performer_sheet=sheet, target_sheet=sheet, resonance=resonance)

        self.assertIsInstance(result, AtonementResult)
        self.assertEqual(result.stage_before, 2)
        # Amount reduced matches authored constant
        self.assertEqual(result.amount_reduced, ATONEMENT_REDUCE_AMOUNT)

    def test_primal_performer_self_target_stage_1_works(self) -> None:
        """Primal-dominant performer can lead Atonement (per spec §4.1 brainstorm)."""
        sheet = CharacterSheetFactory()
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=primal_affinity)
        _set_dominant_affinity(sheet, "Primal")
        with_corruption_at_stage(sheet, resonance, stage=1)

        result = _call(performer_sheet=sheet, target_sheet=sheet, resonance=resonance)

        self.assertIsInstance(result, AtonementResult)
        self.assertEqual(result.stage_before, 1)

    def test_no_affinity_totals_defaults_to_non_abyssal(self) -> None:
        """A sheet with no affinity data falls through without AtonementAffinityRefused."""
        sheet = CharacterSheetFactory()
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=primal_affinity)
        with_corruption_at_stage(sheet, resonance, stage=1)

        # No CharacterAffinityTotal rows — should not raise
        result = _call(performer_sheet=sheet, target_sheet=sheet, resonance=resonance)

        self.assertIsInstance(result, AtonementResult)


class TestAtonementRiteRefusals(TestCase):
    """Gate checks that must refuse the rite."""

    def test_abyssal_performer_refused(self) -> None:
        """Abyssal-dominant performer is refused."""
        sheet = CharacterSheetFactory()
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=primal_affinity)
        _set_dominant_affinity(sheet, "Abyssal")
        with_corruption_at_stage(sheet, resonance, stage=1)

        with self.assertRaises(AtonementAffinityRefused):
            _call(performer_sheet=sheet, target_sheet=sheet, resonance=resonance)

    def test_other_target_refused(self) -> None:
        """Self-targeting only: passing a different sheet is refused."""
        performer = CharacterSheetFactory()
        target = CharacterSheetFactory()
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=primal_affinity)
        _set_dominant_affinity(performer, "Celestial")
        with_corruption_at_stage(target, resonance, stage=1)

        with self.assertRaises(AtonementSelfTargetRequired):
            _call(performer_sheet=performer, target_sheet=target, resonance=resonance)

    def test_stage_0_refused(self) -> None:
        """Stage 0 (no corruption) is refused."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        _set_dominant_affinity(sheet, "Celestial")
        # No corruption setup → stage == 0

        with self.assertRaises(AtonementStageOutOfRange):
            _call(performer_sheet=sheet, target_sheet=sheet, resonance=resonance)

    def test_stage_3_refused(self) -> None:
        """Stage 3+ requires Spec B; foundation refuses."""
        sheet = CharacterSheetFactory()
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=primal_affinity)
        _set_dominant_affinity(sheet, "Celestial")
        with_corruption_at_stage(sheet, resonance, stage=3)

        with self.assertRaises(AtonementStageOutOfRange):
            _call(performer_sheet=sheet, target_sheet=sheet, resonance=resonance)

    def test_stage_4_refused(self) -> None:
        """Stage 4 also out of range."""
        sheet = CharacterSheetFactory()
        primal_affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=primal_affinity)
        _set_dominant_affinity(sheet, "Celestial")
        with_corruption_at_stage(sheet, resonance, stage=4)

        with self.assertRaises(AtonementStageOutOfRange):
            _call(performer_sheet=sheet, target_sheet=sheet, resonance=resonance)


class TestAtonementRitualFactory(TestCase):
    """AtonementRitualFactory produces a valid SERVICE-dispatched Ritual row."""

    def test_factory_creates_valid_ritual(self) -> None:
        from world.magic.constants import RitualExecutionKind
        from world.magic.models import Ritual

        ritual = AtonementRitualFactory()

        self.assertEqual(ritual.name, "Rite of Atonement")
        self.assertEqual(ritual.execution_kind, RitualExecutionKind.SERVICE)
        self.assertEqual(
            ritual.service_function_path,
            "world.magic.services.atonement.perform_atonement_rite",
        )
        self.assertIsNone(ritual.flow)

        # Should be findable in DB
        self.assertTrue(Ritual.objects.filter(name="Rite of Atonement").exists())

    def test_factory_idempotent(self) -> None:
        from world.magic.models import Ritual

        AtonementRitualFactory()
        AtonementRitualFactory()  # second call — get_or_create

        self.assertEqual(Ritual.objects.filter(name="Rite of Atonement").count(), 1)
