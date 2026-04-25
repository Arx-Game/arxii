"""Tests for accrue_corruption + reduce_corruption services (Scope #7, Task 6.3)."""

from unittest import mock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.types import AdvancementOutcome
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory


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


class TestAccrueCorruption(TestCase):
    """accrue_corruption service behaviour."""

    def _call(self, **kwargs):
        from world.magic.services.corruption import accrue_corruption
        from world.magic.types.corruption import CorruptionSource

        defaults = {"source": CorruptionSource.STAFF_GRANT}
        defaults.update(kwargs)
        return accrue_corruption(**defaults)

    def test_increments_both_fields(self) -> None:
        from world.magic.models.aura import CharacterResonance

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()

        result = self._call(character_sheet=sheet, resonance=resonance, amount=10)

        self.assertEqual(result.amount_applied, 10)
        self.assertEqual(result.current_before, 0)
        self.assertEqual(result.current_after, 10)
        self.assertEqual(result.lifetime_before, 0)
        self.assertEqual(result.lifetime_after, 10)

        # Verify DB
        row = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(row.corruption_current, 10)
        self.assertEqual(row.corruption_lifetime, 10)

    def test_no_template_is_noop_for_condition(self) -> None:
        """No authored ConditionTemplate → fields increment, no condition created."""
        from world.conditions.models import ConditionInstance

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()

        result = self._call(character_sheet=sheet, resonance=resonance, amount=100)

        self.assertEqual(result.current_after, 100)
        self.assertIsNone(result.condition_instance)
        self.assertEqual(result.stage_after, 0)
        self.assertEqual(result.advancement_outcome, AdvancementOutcome.NO_CHANGE)
        self.assertFalse(ConditionInstance.objects.filter(target=sheet.character).exists())

    def test_sub_threshold_accrual_creates_no_condition(self) -> None:
        """Accrual below stage-1 threshold does not create condition."""
        from world.conditions.models import ConditionInstance

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        _make_corruption_template(resonance)  # stage 1 threshold = 50

        result = self._call(character_sheet=sheet, resonance=resonance, amount=10)

        self.assertIsNone(result.condition_instance)
        self.assertFalse(ConditionInstance.objects.filter(target=sheet.character).exists())

    def test_lazy_creates_condition_at_stage_1_threshold(self) -> None:
        """Accrual at or above stage-1 threshold creates condition at stage 1."""
        from world.conditions.models import ConditionInstance

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        _make_corruption_template(resonance)  # stage 1 threshold = 50

        result = self._call(character_sheet=sheet, resonance=resonance, amount=50)

        self.assertIsNotNone(result.condition_instance)
        self.assertEqual(result.stage_after, 1)
        self.assertEqual(result.advancement_outcome, AdvancementOutcome.ADVANCED)
        instance = ConditionInstance.objects.get(target=sheet.character)
        self.assertEqual(instance.current_stage.stage_order, 1)

    def test_subsequent_accrual_advances_stage(self) -> None:
        """Second accrual past stage-2 threshold advances the condition."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        _make_corruption_template(resonance)

        # Get to stage 1
        self._call(character_sheet=sheet, resonance=resonance, amount=50)
        # Advance past stage 2 (threshold=200)
        result = self._call(character_sheet=sheet, resonance=resonance, amount=160)

        self.assertEqual(result.stage_after, 2)

    def test_validation_error_on_zero_amount(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with self.assertRaises(ValueError):
            self._call(character_sheet=sheet, resonance=resonance, amount=0)

    def test_validation_error_on_negative_amount(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with self.assertRaises(ValueError):
            self._call(character_sheet=sheet, resonance=resonance, amount=-5)

    def test_result_is_frozen_dataclass(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        result = self._call(character_sheet=sheet, resonance=resonance, amount=5)
        from world.magic.types.corruption import CorruptionAccrualResult

        self.assertIsInstance(result, CorruptionAccrualResult)


class TestReduceCorruption(TestCase):
    """reduce_corruption service behaviour."""

    def _setup_corrupted(self, sheet, resonance, amount=100):
        """Accrue enough to be past stage 1 and return the char_resonance row."""
        from world.magic.services.corruption import accrue_corruption
        from world.magic.types.corruption import CorruptionSource

        _make_corruption_template(resonance)
        accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=amount,
            source=CorruptionSource.STAFF_GRANT,
        )

    def _call(self, **kwargs):
        from world.magic.services.corruption import reduce_corruption
        from world.magic.types.corruption import CorruptionRecoverySource

        defaults = {"source": CorruptionRecoverySource.STAFF_GRANT}
        defaults.update(kwargs)
        return reduce_corruption(**defaults)

    def test_decrements_corruption_current_only(self) -> None:
        from world.magic.models.aura import CharacterResonance

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        self._setup_corrupted(sheet, resonance, amount=100)

        result = self._call(character_sheet=sheet, resonance=resonance, amount=30)

        row = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(row.corruption_current, 70)
        # lifetime should NOT change
        self.assertEqual(row.corruption_lifetime, 100)
        self.assertEqual(result.amount_reduced, 30)

    def test_clamps_at_zero(self) -> None:
        from world.magic.models.aura import CharacterResonance

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        self._setup_corrupted(sheet, resonance, amount=50)

        # Try to reduce by more than current
        result = self._call(character_sheet=sheet, resonance=resonance, amount=999)

        row = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(row.corruption_current, 0)
        self.assertEqual(result.amount_reduced, 50)

    def test_validation_error_on_zero_amount(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=resonance)
        with self.assertRaises(ValueError):
            self._call(character_sheet=sheet, resonance=resonance, amount=0)

    def test_from_decay_flag_skips_decay_call(self) -> None:
        """_from_decay=True must not call decay_condition_severity."""
        from world.magic.models.aura import CharacterResonance

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        self._setup_corrupted(sheet, resonance, amount=100)

        with mock.patch("world.magic.services.corruption.decay_condition_severity") as mock_decay:
            self._call(
                character_sheet=sheet,
                resonance=resonance,
                amount=10,
                _from_decay=True,
            )
            mock_decay.assert_not_called()

        # corruption_current still decremented
        row = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(row.corruption_current, 90)

    def test_result_is_frozen_dataclass(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        self._setup_corrupted(sheet, resonance, amount=100)
        result = self._call(character_sheet=sheet, resonance=resonance, amount=10)
        from world.magic.types.corruption import CorruptionRecoveryResult

        self.assertIsInstance(result, CorruptionRecoveryResult)
