"""Integration tests for the Corruption foundation (Magic Scope #7).

Each test exercises a multi-step slice of the shipped surfaces rather
than a single function in isolation.

Excluded scenarios (waiting on Phase 6.4 / 7.1 unblocking — TechniqueUseResult
extension to expose per-resonance involvement):
- Per-cast accrual via use_technique
- Cast pipeline integration

Those scenarios are gated on accrue_corruption_for_cast being wired into
services/techniques.py, which depends on TechniqueUseResult exposing
per-resonance stat bonus contributions.

Pattern matches src/world/magic/tests/integration/test_soulfray_recovery_flow.py.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import decay_condition_severity
from world.magic.exceptions import ProtagonismLockedError
from world.magic.factories import (
    ResonanceFactory,
    with_corruption_at_stage,
)
from world.magic.models.aura import CharacterResonance
from world.magic.services.atonement import (
    AtonementStageOutOfRange,
    perform_atonement_rite,
)
from world.magic.services.corruption import (
    accrue_corruption,
    reduce_corruption,
)
from world.magic.types.corruption import CorruptionRecoverySource, CorruptionSource

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_EMIT_EVENT_PATH = "world.magic.services.corruption.emit_event"

# Counter to generate unique room names across tests.
_room_counter = 0


def _create_room() -> ObjectDB:
    global _room_counter  # noqa: PLW0603
    _room_counter += 1
    return ObjectDB.objects.create(
        db_key=f"CorruptionTestRoom_{_room_counter}",
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_simple_template(resonance):
    """Create a Corruption ConditionTemplate with default ADVANCE_AT_THRESHOLD stages.

    Uses ConditionStageFactory defaults (no HOLD_OVERFLOW resist check) so
    stage advancement is deterministic in tests.  Thresholds: 50, 200, 500,
    1000, 1500 — matching with_corruption_at_stage defaults.
    """
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name} simple)",
        has_progression=True,
        corruption_resonance=resonance,
    )
    thresholds = [50, 200, 500, 1000, 1500]
    stages = []
    for i, threshold in enumerate(thresholds, start=1):
        stages.append(
            ConditionStageFactory(
                condition=template,
                stage_order=i,
                severity_threshold=threshold,
            )
        )
    return template, stages


# ---------------------------------------------------------------------------
# Integration scenarios
# ---------------------------------------------------------------------------


class AccrueCorruptionStageAdvancementTests(TestCase):
    """Scenario 1: direct accrue_corruption advances stages as thresholds cross."""

    def test_accrue_past_stage1_then_stage2(self) -> None:
        """Accruing past stage 1 (50) then stage 2 (200) creates and advances condition."""
        resonance = ResonanceFactory()
        _make_simple_template(resonance)
        sheet = CharacterSheetFactory()

        # Stage 1 creation at threshold=50
        result1 = accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=50,
            source=CorruptionSource.STAFF_GRANT,
        )
        assert result1.stage_after == 1
        assert ConditionInstance.objects.filter(target=sheet.character).exists()

        # Stage 2 advancement: need 160 more to cross threshold=200
        result2 = accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=160,
            source=CorruptionSource.STAFF_GRANT,
        )
        assert result2.stage_after == 2

        # Lifetime tracks both calls
        char_res = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        assert char_res.corruption_lifetime == 210
        assert char_res.corruption_current == 210


class LifetimeMonotonicTests(TestCase):
    """Scenario 2: lifetime is monotonic — accrue + reduce leaves lifetime unchanged."""

    def test_lifetime_does_not_shrink_on_reduce(self) -> None:
        resonance = ResonanceFactory()
        _make_simple_template(resonance)
        sheet = CharacterSheetFactory()

        accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=100,
            source=CorruptionSource.STAFF_GRANT,
        )

        reduce_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=50,
            source=CorruptionRecoverySource.STAFF_GRANT,
        )

        char_res = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        assert char_res.corruption_current == 50
        assert char_res.corruption_lifetime == 100

        reduce_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=50,
            source=CorruptionRecoverySource.STAFF_GRANT,
        )

        char_res.refresh_from_db()
        assert char_res.corruption_current == 0
        assert char_res.corruption_lifetime == 100  # still monotonic


class LazyConditionCreationTests(TestCase):
    """Scenario 3: condition is only created at the stage-1 threshold boundary."""

    def test_below_threshold_no_condition(self) -> None:
        resonance = ResonanceFactory()
        _make_simple_template(resonance)
        sheet = CharacterSheetFactory()

        # 49 — below the 50 threshold
        result = accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=49,
            source=CorruptionSource.STAFF_GRANT,
        )
        assert result.condition_instance is None
        assert not ConditionInstance.objects.filter(target=sheet.character).exists()

    def test_at_threshold_creates_condition(self) -> None:
        resonance = ResonanceFactory()
        _make_simple_template(resonance)
        sheet = CharacterSheetFactory()

        # 49 sub-threshold, then 1 more tips it over
        accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=49,
            source=CorruptionSource.STAFF_GRANT,
        )
        result = accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=1,
            source=CorruptionSource.STAFF_GRANT,
        )
        assert result.condition_instance is not None
        assert result.stage_after == 1
        assert ConditionInstance.objects.filter(target=sheet.character).count() == 1


class NoTemplateNoOpTests(TestCase):
    """Scenario 4: resonance with no Corruption template — fields increment, no condition."""

    def test_no_template_increments_fields_no_condition(self) -> None:
        resonance = ResonanceFactory()  # no ConditionTemplate authored
        sheet = CharacterSheetFactory()

        result = accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=200,
            source=CorruptionSource.STAFF_GRANT,
        )

        char_res = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        assert char_res.corruption_current == 200
        assert char_res.corruption_lifetime == 200
        assert result.condition_instance is None
        assert not ConditionInstance.objects.filter(target=sheet.character).exists()


class ProtagonismLockTests(TestCase):
    """Scenario 5: lock at stage 5 and lock-exit on reduce below stage 5."""

    def test_stage_5_locks_protagonism(self) -> None:
        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        sheet.__dict__.pop("is_protagonism_locked", None)

        assert sheet.is_protagonism_locked is True

    def test_reduce_below_stage_5_restores_protagonism(self) -> None:
        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        sheet.__dict__.pop("is_protagonism_locked", None)
        assert sheet.is_protagonism_locked is True

        # with_corruption_at_stage sets corruption_current to 1500 (stage 5 threshold).
        # Reduce by 600 drops it to 900, below stage 4 threshold (1000) → stage 3 → unlocked.
        reduce_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=600,
            source=CorruptionRecoverySource.STAFF_GRANT,
        )

        # Invalidate cached_property then recheck
        sheet.__dict__.pop("is_protagonism_locked", None)
        assert sheet.is_protagonism_locked is False


class ConsumerGateSanityTest(TestCase):
    """Scenario 6: consumer gate — spend_xp_on_unlock blocked for subsumed sheet."""

    def test_spend_xp_raises_protagonism_locked_error(self) -> None:
        from world.classes.factories import CharacterClassLevelFactory
        from world.progression.services import spend_xp_on_unlock

        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        sheet.__dict__.pop("is_protagonism_locked", None)
        character = sheet.character
        unlock = CharacterClassLevelFactory()

        with self.assertRaises(ProtagonismLockedError):
            spend_xp_on_unlock(character, unlock)


class AtonementRiteTests(TestCase):
    """Scenarios 7 + 8: Atonement Rite full path and stage-3+ refusal."""

    def test_atonement_reduces_stage_1_corruption(self) -> None:
        """Full path: stage 1 corruption → Atonement → corruption_current drops."""
        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        with_corruption_at_stage(sheet, resonance, stage=1)
        # stage 1 sets corruption_current = 50

        result = perform_atonement_rite(
            performer_sheet=sheet,
            target_sheet=sheet,
            resonance=resonance,
        )

        assert result.amount_reduced > 0
        char_res = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        # ATONEMENT_REDUCE_AMOUNT=100 > 50, so clamped to 0
        assert char_res.corruption_current == 0

    def test_atonement_refused_for_stage_3(self) -> None:
        """Stage 3 corruption — AtonementStageOutOfRange is raised."""
        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        with_corruption_at_stage(sheet, resonance, stage=3)

        with self.assertRaises(AtonementStageOutOfRange):
            perform_atonement_rite(
                performer_sheet=sheet,
                target_sheet=sheet,
                resonance=resonance,
            )


class DecaySyncTests(TestCase):
    """Scenario 9: decay_condition_severity syncs corruption_current."""

    def test_decay_syncs_corruption_current(self) -> None:
        """ConditionInstance at stage 1 (severity 50) with corruption_current=50.
        decay_condition_severity(instance, 10) drops corruption_current to 40.
        corruption_lifetime unchanged.
        """
        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        with_corruption_at_stage(sheet, resonance, stage=1)
        # stage 1: corruption_current = 50, corruption_lifetime = 50

        char_res = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        assert char_res.corruption_current == 50
        assert char_res.corruption_lifetime == 50

        instance = ConditionInstance.objects.get(
            target=sheet.character,
            condition__corruption_resonance=resonance,
        )

        decay_condition_severity(instance, 10)

        char_res.refresh_from_db()
        assert char_res.corruption_current == 40
        assert char_res.corruption_lifetime == 50  # monotonic — unchanged


class RiskTransparencyEventTests(TestCase):
    """Scenario 10: risk-transparency events fire on stage 3 and stage 5 entry."""

    def test_corruption_warning_emitted_on_stage_3_entry(self) -> None:
        """Accruing past the stage-3 threshold fires CORRUPTION_WARNING."""
        from flows.constants import EventName

        resonance = ResonanceFactory()
        _make_simple_template(resonance)
        sheet = CharacterSheetFactory()

        # Give the character a location so emit_event fires (skipped when location=None).
        room = _create_room()
        sheet.character.location = room

        # Bring to stage 2 (threshold=200)
        accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=200,
            source=CorruptionSource.STAFF_GRANT,
        )

        emitted_event_names: list[str] = []
        import world.magic.services.corruption as corruption_mod

        original_emit = corruption_mod.emit_event

        def capturing_emit(event_name, payload, location, **kwargs):
            emitted_event_names.append(event_name)
            return original_emit(event_name, payload, location, **kwargs)

        with patch(_EMIT_EVENT_PATH, side_effect=capturing_emit):
            # Cross from stage 2 to stage 3 (threshold=500, need 300 more)
            accrue_corruption(
                character_sheet=sheet,
                resonance=resonance,
                amount=310,
                source=CorruptionSource.STAFF_GRANT,
            )

        assert EventName.CORRUPTION_WARNING in emitted_event_names

    def test_protagonism_locked_emitted_on_stage_5_entry(self) -> None:
        """Accruing past the stage-5 threshold fires PROTAGONISM_LOCKED."""
        from flows.constants import EventName

        resonance = ResonanceFactory()
        _make_simple_template(resonance)
        sheet = CharacterSheetFactory()
        room = _create_room()
        sheet.character.location = room

        # Bring to stage 4 (threshold=1000)
        accrue_corruption(
            character_sheet=sheet,
            resonance=resonance,
            amount=1000,
            source=CorruptionSource.STAFF_GRANT,
        )

        emitted_event_names: list[str] = []
        import world.magic.services.corruption as corruption_mod

        original_emit = corruption_mod.emit_event

        def capturing_emit(event_name, payload, location, **kwargs):
            emitted_event_names.append(event_name)
            return original_emit(event_name, payload, location, **kwargs)

        with patch(_EMIT_EVENT_PATH, side_effect=capturing_emit):
            # Cross stage 5 threshold (1500, need 510 more)
            accrue_corruption(
                character_sheet=sheet,
                resonance=resonance,
                amount=510,
                source=CorruptionSource.STAFF_GRANT,
            )

        assert EventName.PROTAGONISM_LOCKED in emitted_event_names
