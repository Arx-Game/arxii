"""Services for the Corruption foundation (Magic Scope #7)."""

from __future__ import annotations

from django.db import transaction

from flows.constants import EventName
from flows.emit import emit_event
from world.character_sheets.models import CharacterSheet
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import advance_condition_severity, decay_condition_severity
from world.conditions.types import AdvancementOutcome
from world.magic.models.affinity import Resonance
from world.magic.models.aura import CharacterResonance
from world.magic.models.corruption_config import CorruptionConfig
from world.magic.types.corruption import (
    CorruptionAccrualResult,
    CorruptionAccruedPayload,
    CorruptionAccruingPayload,
    CorruptionCause,
    CorruptionRecoveryResult,
    CorruptionRecoverySource,
    CorruptionReducedPayload,
    CorruptionSource,
    CorruptionWarningPayload,
    ProtagonismLockedPayload,
    ProtagonismRestoredPayload,
)

# Stage constants — spec §2.1 terminal stage
_TERMINAL_STAGE = 5
_WARNING_STAGES = (3, 4)


def get_corruption_config() -> CorruptionConfig:
    """Lazy-create the CorruptionConfig singleton at pk=1."""
    config, _ = CorruptionConfig.objects.get_or_create(pk=1)
    return config


def _resolve_character(character_sheet: CharacterSheet) -> object:
    """Resolve a CharacterSheet to its character ObjectDB.

    CharacterSheet.character is a OneToOneField to ObjectDB (primary_key=True),
    so sheet.character is the ObjectDB instance directly.
    """
    return character_sheet.character


def _resolve_location(character_sheet: CharacterSheet) -> object:
    """Resolve the character's current location for event emission."""
    character = _resolve_character(character_sheet)
    if character is None:
        return None
    return getattr(character, "location", None)  # noqa: GETATTR_LITERAL


def _make_no_op_result(  # noqa: PLR0913
    *,
    resonance: Resonance,
    amount: int,
    current_before: int,
    current_after: int,
    lifetime_before: int,
    lifetime_after: int,
) -> CorruptionAccrualResult:
    """Build a CorruptionAccrualResult for a no-op case (no condition created)."""
    return CorruptionAccrualResult(
        resonance=resonance,
        amount_applied=amount,
        current_before=current_before,
        current_after=current_after,
        lifetime_before=lifetime_before,
        lifetime_after=lifetime_after,
        stage_before=0,
        stage_after=0,
        advancement_outcome=AdvancementOutcome.NO_CHANGE,
        condition_instance=None,
    )


def _emit_risk_transparency_events(
    *,
    outcome: AdvancementOutcome,
    stage_after: int,
    character_sheet: CharacterSheet,
    resonance: Resonance,
    location: object,
) -> None:
    """Emit CORRUPTION_WARNING or PROTAGONISM_LOCKED on stage advancement."""
    if outcome != AdvancementOutcome.ADVANCED:
        return
    if stage_after in _WARNING_STAGES:
        severity_label = "ADVISORY" if stage_after == _WARNING_STAGES[0] else "URGENT"
        warning_payload = CorruptionWarningPayload(
            character_sheet=character_sheet,
            resonance=resonance,
            stage=stage_after,
            severity_label=severity_label,
        )
        if location is not None:
            emit_event(EventName.CORRUPTION_WARNING, warning_payload, location=location)
    elif stage_after == _TERMINAL_STAGE:
        character_sheet.__dict__.pop("is_protagonism_locked", None)
        lock_payload = ProtagonismLockedPayload(
            character_sheet=character_sheet,
            resonance=resonance,
            cause=CorruptionCause.STAGE_5_SUBSUMPTION,
        )
        if location is not None:
            emit_event(EventName.PROTAGONISM_LOCKED, lock_payload, location=location)


@transaction.atomic
def accrue_corruption(  # noqa: PLR0913
    *,
    character_sheet: CharacterSheet,
    resonance: Resonance,
    amount: int,
    source: CorruptionSource,
    technique_use: object = None,  # noqa: ARG001 — forwarded by accrue_corruption_for_cast
    redirect_origin: CharacterSheet | None = None,
) -> CorruptionAccrualResult:
    """Apply ``amount`` corruption to (sheet, resonance), resolve stage atomically.

    Steps:
    1. Emit CORRUPTION_ACCRUING (pre-mutation, fire-and-forget for now).
    2. Increment CharacterResonance.corruption_current + corruption_lifetime.
    3. Look up per-resonance ConditionTemplate.
    4. Lazy-create or advance the ConditionInstance.
    5. Emit risk-transparency events (WARNING / PROTAGONISM_LOCKED) on stage change.
    6. Emit CORRUPTION_ACCRUED (post-mutation).

    ``source`` is part of the API signature for future audit-trail integration;
    it is not written to any row in this phase.
    ``technique_use`` is forwarded by accrue_corruption_for_cast; stored here
    for future per-cast audit rows.
    ``redirect_origin`` is the Soul Tether source sheet when source=SPEC_B_REDIRECT.
    """
    if amount <= 0:
        msg = f"amount must be > 0, got {amount}"
        raise ValueError(msg)

    # Pre-mutation event for future Spec B interception
    pre_payload = CorruptionAccruingPayload(
        character_sheet=character_sheet,
        resonance=resonance,
        amount=amount,
        source=source,
        redirect_origin=redirect_origin,
    )
    location = _resolve_location(character_sheet)
    if location is not None:
        emit_event(EventName.CORRUPTION_ACCRUING, pre_payload, location=location)

    # Increment fields
    char_resonance, _ = CharacterResonance.objects.select_for_update().get_or_create(
        character_sheet=character_sheet,
        resonance=resonance,
    )
    current_before = char_resonance.corruption_current
    lifetime_before = char_resonance.corruption_lifetime
    char_resonance.corruption_current = current_before + amount
    char_resonance.corruption_lifetime = lifetime_before + amount
    char_resonance.save(update_fields=["corruption_current", "corruption_lifetime"])

    # Look up the per-resonance Corruption ConditionTemplate
    template = ConditionTemplate.objects.filter(corruption_resonance=resonance).first()

    # No-op when no Corruption content authored for this resonance
    if template is None:
        result = _make_no_op_result(
            resonance=resonance,
            amount=amount,
            current_before=current_before,
            current_after=char_resonance.corruption_current,
            lifetime_before=lifetime_before,
            lifetime_after=char_resonance.corruption_lifetime,
        )
        if location is not None:
            emit_event(
                EventName.CORRUPTION_ACCRUED,
                CorruptionAccruedPayload(result=result),
                location=location,
            )
        return result

    # Find or lazy-create the ConditionInstance
    character = _resolve_character(character_sheet)
    instance = ConditionInstance.objects.filter(
        target=character,
        condition=template,
    ).first()

    stage_1 = template.stages.filter(stage_order=1).first()
    stage_1_threshold = stage_1.severity_threshold if stage_1 else None

    stage_before = 0
    stage_after = 0
    outcome = AdvancementOutcome.NO_CHANGE

    if instance is None:
        if stage_1_threshold is not None and char_resonance.corruption_current >= stage_1_threshold:
            # Lazy-create at stage 1
            instance = ConditionInstance.objects.create(
                target=character,
                condition=template,
                current_stage=stage_1,
                severity=char_resonance.corruption_current,
            )
            stage_after = 1
            outcome = AdvancementOutcome.ADVANCED
            stage_before = 0
        else:
            # Sub-threshold accrual — no condition created yet
            result = _make_no_op_result(
                resonance=resonance,
                amount=amount,
                current_before=current_before,
                current_after=char_resonance.corruption_current,
                lifetime_before=lifetime_before,
                lifetime_after=char_resonance.corruption_lifetime,
            )
            if location is not None:
                emit_event(
                    EventName.CORRUPTION_ACCRUED,
                    CorruptionAccruedPayload(result=result),
                    location=location,
                )
            return result
    else:
        # Sync severity with corruption_current and advance via Scope 3+6 path
        stage_before = instance.current_stage.stage_order if instance.current_stage else 0
        delta = char_resonance.corruption_current - instance.severity
        if delta > 0:
            advance_result = advance_condition_severity(instance, delta)
            stage_after = advance_result.new_stage.stage_order if advance_result.new_stage else 0
            outcome = advance_result.outcome
        else:
            stage_after = stage_before

    _emit_risk_transparency_events(
        outcome=outcome,
        stage_after=stage_after,
        character_sheet=character_sheet,
        resonance=resonance,
        location=location,
    )

    result = CorruptionAccrualResult(
        resonance=resonance,
        amount_applied=amount,
        current_before=current_before,
        current_after=char_resonance.corruption_current,
        lifetime_before=lifetime_before,
        lifetime_after=char_resonance.corruption_lifetime,
        stage_before=stage_before,
        stage_after=stage_after,
        advancement_outcome=outcome,
        condition_instance=instance,
    )
    if location is not None:
        emit_event(
            EventName.CORRUPTION_ACCRUED,
            CorruptionAccruedPayload(result=result),
            location=location,
        )
    return result


@transaction.atomic
def reduce_corruption(
    *,
    character_sheet: CharacterSheet,
    resonance: Resonance,
    amount: int,
    source: CorruptionRecoverySource,  # noqa: ARG001 — part of the API signature for audit trail integration
    ritual: object = None,  # noqa: ARG001 — reserved for future ritual-source audit rows
    _from_decay: bool = False,
) -> CorruptionRecoveryResult:
    """Reduce corruption_current on (sheet, resonance), sync the condition.

    ``_from_decay=True`` skips the call to decay_condition_severity to prevent
    infinite recursion when Scope 6 decay invokes this service.

    Note: lifetime totals are intentionally NOT reduced — they are monotonic
    per spec §2.2.
    """
    if amount <= 0:
        msg = f"amount must be > 0, got {amount}"
        raise ValueError(msg)

    char_resonance = CharacterResonance.objects.select_for_update().get(
        character_sheet=character_sheet,
        resonance=resonance,
    )
    current_before = char_resonance.corruption_current
    char_resonance.corruption_current = max(0, current_before - amount)
    char_resonance.save(update_fields=["corruption_current"])
    actual_reduction = current_before - char_resonance.corruption_current

    character = _resolve_character(character_sheet)
    instance = ConditionInstance.objects.filter(
        target=character,
        condition__corruption_resonance=resonance,
    ).first()

    stage_before = instance.current_stage.stage_order if instance and instance.current_stage else 0
    condition_resolved = False
    stage_after = stage_before

    if instance is not None and not _from_decay:
        decay_result = decay_condition_severity(
            instance, actual_reduction, _skip_corruption_sync=True
        )
        condition_resolved = decay_result.resolved
        stage_after = decay_result.new_stage.stage_order if decay_result.new_stage else 0

    # Lock-exit event
    location = _resolve_location(character_sheet)
    if stage_before == _TERMINAL_STAGE and stage_after < _TERMINAL_STAGE:
        character_sheet.__dict__.pop("is_protagonism_locked", None)
        if location is not None:
            emit_event(
                EventName.PROTAGONISM_RESTORED,
                ProtagonismRestoredPayload(
                    character_sheet=character_sheet,
                    cause=CorruptionCause.STAGE_5_RECOVERED,
                ),
                location=location,
            )

    result = CorruptionRecoveryResult(
        resonance=resonance,
        amount_reduced=actual_reduction,
        current_before=current_before,
        current_after=char_resonance.corruption_current,
        stage_before=stage_before,
        stage_after=stage_after,
        condition_resolved=condition_resolved,
    )
    if location is not None:
        emit_event(
            EventName.CORRUPTION_REDUCED,
            CorruptionReducedPayload(result=result),
            location=location,
        )
    return result
