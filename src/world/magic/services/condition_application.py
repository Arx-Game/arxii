"""Shared condition-application service for technique casting.

Extracted from CombatTechniqueResolver._apply_conditions so that both combat
and standalone cast paths call identical code. Callers are responsible for
resolving targets before calling this function — the combat-vs-standalone
split is in target resolution, not in condition application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.services import bulk_apply_conditions

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.types import AppliedConditionResult
    from world.magic.models.techniques import Technique


def apply_technique_conditions(
    *,
    technique: Technique,
    success_level: int,
    eff_intensity: int,
    targets_by_kind: dict[str, list[ObjectDB]],  # noqa: OBJECTDB_PARAM
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> list[AppliedConditionResult]:
    """Apply technique-authored conditions to pre-resolved targets.

    Iterates all ``TechniqueAppliedCondition`` rows on *technique*, skips rows
    whose ``minimum_success_level`` exceeds *success_level*, and for each row
    applies the condition to every ``ObjectDB`` in
    ``targets_by_kind.get(row.target_kind, [])``.

    Severity and duration are computed via the row's formula methods using
    *eff_intensity* and *success_level*.  The full batch is handed to
    ``bulk_apply_conditions`` in a single call and the results are mapped to
    ``AppliedConditionResult`` instances.

    Args:
        technique: The ``Technique`` whose authored condition rows are iterated.
        success_level: The check success level (SL) from the cast roll.
        eff_intensity: The effective intensity (injected power + pull bumps).
        targets_by_kind: Mapping from ``ConditionTargetKind`` value (str) to a
            list of already-resolved ``ObjectDB`` targets.  Callers build this
            before calling here — target resolution differs between combat
            (``_resolve_condition_target``) and standalone casts.
        source_character: The caster's ``ObjectDB``.  Forwarded to
            ``bulk_apply_conditions`` as ``source_character``.

    Returns:
        List of ``AppliedConditionResult``, one per ``BulkConditionApplication``
        submitted, in the same order.  Empty list when no rows pass the SL gate
        or all resolved target lists are empty.
    """
    from world.combat.types import AppliedConditionResult  # noqa: PLC0415
    from world.conditions.types import BulkConditionApplication  # noqa: PLC0415

    rows = list(technique.condition_applications.select_related("condition").all())
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
    return out
