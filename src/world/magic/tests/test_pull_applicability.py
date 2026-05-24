"""Tests for pull applicability computation.

See world/magic/services/pull_applicability.py.
"""

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import InapplicabilityReason, TargetKind
from world.magic.factories import ResonanceFactory, TechniqueFactory, ThreadFactory
from world.magic.services.pull_applicability import (
    PullActionContext,
    ThreadApplicability,
    compute_thread_applicability,
)


def _empty_context(**overrides: object) -> PullActionContext:
    """Return a context with all fields None, with optional overrides."""
    defaults: dict[str, object] = {
        "technique": None,
        "effect_type_id": None,
        "target_object_id": None,
        "target_persona_id": None,
        "scene_id": None,
    }
    defaults.update(overrides)
    return PullActionContext(**defaults)  # type: ignore[arg-type]


class ComputeThreadApplicabilityTests(TestCase):
    """Core tests for compute_thread_applicability."""

    def test_returns_one_row_per_thread(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        ThreadFactory(owner=sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 2)

    def test_returns_thread_applicability_instances(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertIsInstance(rows[0], ThreadApplicability)

    def test_retired_threads_excluded(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet, retired_at=timezone.now())
        ThreadFactory(owner=sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)

    def test_threads_from_other_owners_excluded(self) -> None:
        sheet = CharacterSheetFactory()
        other_sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        ThreadFactory(owner=other_sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 1)

    def test_empty_result_when_no_threads(self) -> None:
        sheet = CharacterSheetFactory()
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(rows, [])

    def test_trait_thread_applicable_when_no_technique_in_context(self) -> None:
        """Non-TECHNIQUE threads are applicable when no technique is in context."""
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)  # TRAIT kind by default
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)


class AnchoredOnOtherTechniqueRuleTests(TestCase):
    """Tests for the ANCHORED_ON_OTHER_TECHNIQUE applicability rule."""

    def test_technique_thread_applicable_when_same_technique_in_context(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        technique = TechniqueFactory()
        thread = ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )
        context = _empty_context(technique=technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].thread, thread)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_technique_thread_inapplicable_when_different_technique_in_context(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        anchored_technique = TechniqueFactory()
        other_technique = TechniqueFactory()
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=anchored_technique,
        )
        context = _empty_context(technique=other_technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.ANCHORED_ON_OTHER_TECHNIQUE.value)

    def test_technique_thread_inapplicable_when_no_technique_in_context(self) -> None:
        """A TECHNIQUE-kind thread cannot apply when no technique is specified."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        technique = TechniqueFactory()
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )
        context = _empty_context()  # no technique
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.ANCHORED_ON_OTHER_TECHNIQUE.value)

    def test_non_technique_thread_unaffected_by_technique_in_context(self) -> None:
        """TRAIT-kind threads are not filtered by technique context."""
        sheet = CharacterSheetFactory()
        technique = TechniqueFactory()
        ThreadFactory(owner=sheet)  # TRAIT kind
        context = _empty_context(technique=technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)

    def test_mixed_threads_correct_applicability(self) -> None:
        """TECHNIQUE thread for the right technique + TRAIT thread both applicable."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        technique = TechniqueFactory()
        # Thread anchored to the context technique — should be applicable.
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )
        # TRAIT thread — always applicable regardless of technique context.
        ThreadFactory(owner=sheet)
        context = _empty_context(technique=technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.applicable for r in rows))

    def test_wrong_technique_and_trait_thread_mixed(self) -> None:
        """TECHNIQUE thread for the wrong technique is inapplicable; TRAIT is not."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        anchored_technique = TechniqueFactory()
        context_technique = TechniqueFactory()
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=anchored_technique,
        )
        ThreadFactory(owner=sheet)  # TRAIT — always applicable
        context = _empty_context(technique=context_technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 2)
        applicable = [r for r in rows if r.applicable]
        inapplicable = [r for r in rows if not r.applicable]
        self.assertEqual(len(applicable), 1)
        self.assertEqual(len(inapplicable), 1)
        self.assertEqual(
            inapplicable[0].reason, InapplicabilityReason.ANCHORED_ON_OTHER_TECHNIQUE.value
        )
