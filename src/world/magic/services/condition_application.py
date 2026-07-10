"""Shared condition-application service for technique casting.

Extracted from CombatTechniqueResolver._apply_conditions so that both combat
and standalone cast paths call identical code. Callers are responsible for
resolving targets before calling this function — the combat-vs-standalone
split is in target resolution, not in condition application.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from world.checks.services import perform_check
from world.conditions.services import (
    bulk_apply_conditions,
    get_condition_instance,
    remove_condition,
)
from world.conditions.types import (
    AppliedConditionResult,
    ApplyConditionResult,
    BulkConditionApplication,
    RemovedConditionResult,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models.techniques import Technique


def apply_technique_conditions(  # noqa: PLR0913 - cohesive condition-application params
    *,
    technique: Technique,
    success_level: int,
    eff_intensity: int,
    targets_by_kind: dict[str, list[ObjectDB]],  # noqa: OBJECTDB_PARAM
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
    applied_condition_rows: Iterable | None = None,
    position_params: dict[str, int] | None = None,
) -> list[AppliedConditionResult]:
    """Apply authored applied-condition rows to pre-resolved targets.

    Iterates the applied-condition rows, skips rows whose ``minimum_success_level``
    exceeds *success_level*, and for each row applies the condition to every
    ``ObjectDB`` in ``targets_by_kind.get(row.target_kind, [])``.

    Severity and duration are computed via the row's formula methods using
    *eff_intensity* and *success_level*.  The full batch is handed to
    ``bulk_apply_conditions`` in a single call and the results are mapped to
    ``AppliedConditionResult`` instances.

    Args:
        technique: The ``Technique`` being cast. Provenance — forwarded to
            ``bulk_apply_conditions`` as ``source_technique`` so the resulting
            condition instances point at the cast technique. (Also the default
            source of rows when ``applied_condition_rows`` is omitted.)
        success_level: The check success level (SL) from the cast roll.
        eff_intensity: The effective intensity (injected power + pull bumps).
        targets_by_kind: Mapping from ``ConditionTargetKind`` value (str) to a
            list of already-resolved ``ObjectDB`` targets.  Callers build this
            before calling here — target resolution differs between combat
            (``_resolve_condition_target``) and standalone casts.
        source_character: The caster's ``ObjectDB``.  Forwarded to
            ``bulk_apply_conditions`` as ``source_character``.
        applied_condition_rows: Optional override for the rows to apply. When
            ``None`` (the default for every original caller — combat + standalone
            casts), rows are read from ``technique.condition_applications``. When
            provided (the #1582 signature-bonus seam), the given rows are applied
            *as if* authored on the cast technique — they share the abstract
            ``AbstractAppliedCondition`` interface (``compute_severity`` /
            ``compute_duration_rounds`` / ``target_kind`` / ``stack_count``), and
            provenance still points at *technique*. SHARED with the technique's own
            conditions AND combat — keep the default branch byte-identical.

    Returns:
        List of ``AppliedConditionResult``, one per ``BulkConditionApplication``
        submitted, in the same order.  Empty list when no rows pass the SL gate
        or all resolved target lists are empty.
    """
    if applied_condition_rows is None:
        rows = list(technique.condition_applications.select_related("condition").all())
    else:
        rows = list(applied_condition_rows)
    if not rows:
        return []

    bulk_applications: list[BulkConditionApplication] = []
    for row in rows:
        if success_level < row.minimum_success_level:
            continue
        targets = targets_by_kind.get(row.target_kind, [])
        for target in targets:
            severity = row.compute_severity(
                effective_power=eff_intensity,
                success_level=success_level,
            )
            duration = row.compute_duration_rounds(
                effective_power=eff_intensity,
                success_level=success_level,
            )
            bulk_applications.append(
                BulkConditionApplication(
                    target=target,
                    template=row.condition,
                    severity=severity,
                    duration_rounds=duration,
                    stack_count=row.stack_count,
                )
            )

    if not bulk_applications:
        return []

    bulk_results = bulk_apply_conditions(
        bulk_applications,
        source_character=source_character,
        source_technique=technique,
    )
    out: list[AppliedConditionResult] = []
    for app, result in zip(bulk_applications, bulk_results, strict=True):
        out.append(
            AppliedConditionResult(
                target=app.target,
                condition=app.template,
                severity_applied=app.severity,
                duration_rounds=app.duration_rounds,
                success=result.success,
            )
        )

    # #2019: Set cast-time position FKs on the created ConditionInstances.
    if position_params:
        _apply_position_params_to_instances(bulk_results, position_params)

    return out


def _apply_position_params_to_instances(
    bulk_results: list[ApplyConditionResult],
    position_params: dict[str, int],
) -> None:
    """Set cast-time position FKs on created ConditionInstances (#2019).

    The handlers (move_position_on_condition, create_obstacle_on_condition,
    force_move_target_on_condition, create_zone_hazard_on_condition) read
    these from payload.instance instead of the static step-param placeholders.
    """
    dest_id = position_params.get("destination_position_id")
    pos_a_id = position_params.get("position_a_id")
    pos_b_id = position_params.get("position_b_id")
    for result in bulk_results:
        if result.instance is None:
            continue
        update_fields: list[str] = []
        if dest_id:
            result.instance.cast_destination_id = dest_id
            update_fields.append("cast_destination_id")
        if pos_a_id:
            result.instance.cast_position_a_id = pos_a_id
            update_fields.append("cast_position_a_id")
        if pos_b_id:
            result.instance.cast_position_b_id = pos_b_id
            update_fields.append("cast_position_b_id")
        if update_fields:
            result.instance.save(update_fields=update_fields)


def remove_technique_conditions(
    *,
    technique: Technique,
    success_level: int,
    targets_by_kind: dict[str, list[ObjectDB]],  # noqa: OBJECTDB_PARAM
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> list[RemovedConditionResult]:
    """Remove technique-authored conditions from pre-resolved targets (dispel/cleanse).

    The removal sibling of :func:`apply_technique_conditions`. Iterates all
    ``TechniqueRemovedCondition`` rows on *technique* and, for each row passing the
    cast success-level gate, attempts to strip the named condition from every
    ``ObjectDB`` in ``targets_by_kind.get(row.target_kind, [])``.

    Three independent gates per target, evaluated in order:
      1. Row cast-SL gate: ``success_level < row.minimum_success_level`` skips the row
         entirely (mirrors the apply path at ``condition_application.py``). A botched
         cast (SL 0) removes nothing; SL >= 1 passes the default.
      2. ``can_be_dispelled`` hard gate: a condition whose template has
         ``can_be_dispelled=False`` is a no-op (skipped, never an error).
      3. Opposed cure check: when ``row.condition.cure_check_type`` is set, rolls
         ``perform_check(source_character, cure_check_type, cure_difficulty)``. Removal
         succeeds iff ``check_result.success_level > 0``; otherwise it is resisted (no-op
         for that target, cast continues). When ``cure_check_type`` is null, removal
         proceeds unconditionally (uncontested dispel).

    Delegates to :func:`world.conditions.services.remove_condition`, which handles
    stack decrement (``remove_all_stacks=False``), ``CONDITION_REMOVED`` emission,
    deferred-death resolution, and stories re-evaluation.

    Args:
        technique: The ``Technique`` whose ``removed_conditions`` rows are iterated.
        success_level: The cast technique's check success level (SL).
        targets_by_kind: Mapping from ``ConditionTargetKind`` value (str) to resolved
            ``ObjectDB`` targets. Callers build this before calling.
        source_character: The caster's ``ObjectDB``, used as the opposed-cure-check
            roller.

    Returns:
        List of ``RemovedConditionResult``, one per (row, target) attempted, in order.
        Empty when no rows pass the SL gate or all resolved target lists are empty.
    """
    rows = list(
        technique.removed_conditions.select_related("condition", "condition__cure_check_type").all()
    )
    if not rows:
        return []

    out: list[RemovedConditionResult] = []
    for row in rows:
        # Gate 1: cast success-level gate (mirrors the apply path).
        if success_level < row.minimum_success_level:
            continue
        condition = row.condition
        targets = targets_by_kind.get(row.target_kind, [])
        out.extend(
            _attempt_removal(
                target=target,
                condition=condition,
                remove_all_stacks=row.remove_all_stacks,
                source_character=source_character,
            )
            for target in targets
        )
    return out


def _attempt_removal(
    *,
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    condition,
    remove_all_stacks: bool,
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> RemovedConditionResult:
    """Resolve gates 2-4 for one (target, condition) and perform the removal."""
    # Gate 2: can_be_dispelled hard gate.
    if not condition.can_be_dispelled:
        return RemovedConditionResult(
            target=target, condition=condition, success=False, skipped_reason="not_dispellable"
        )

    # Absent condition: nothing to remove.
    if get_condition_instance(target, condition) is None:
        return RemovedConditionResult(
            target=target, condition=condition, success=False, skipped_reason="not_present"
        )

    # Gate 3: opposed cure check (only when the condition defines one).
    cure_check_type = condition.cure_check_type
    if cure_check_type is not None:
        check_result = perform_check(
            source_character,
            cure_check_type,
            condition.cure_difficulty,
        )
        if check_result.success_level <= 0:
            return RemovedConditionResult(
                target=target, condition=condition, success=False, skipped_reason="resisted"
            )

    removed = remove_condition(target, condition, remove_all_stacks=remove_all_stacks)
    return RemovedConditionResult(
        target=target,
        condition=condition,
        success=removed,
        skipped_reason="" if removed else "not_present",
    )
