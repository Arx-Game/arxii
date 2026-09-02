"""Shared condition-application service for technique casting.

Extracted from CombatTechniqueResolver._apply_conditions so that both combat
and standalone cast paths call identical code. Callers are responsible for
resolving targets before calling this function — the combat-vs-standalone
split is in target resolution, not in condition application.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import TYPE_CHECKING, Any

from world.checks.services import perform_check_with_modifiers
from world.conditions.services import (
    bulk_apply_conditions,
    get_condition_instance,
    remove_condition,
)
from world.conditions.types import (
    AppliedConditionResult,
    BulkConditionApplication,
    RemovedConditionResult,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models.techniques import Technique
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)


def _build_bulk_applications_for_row(  # noqa: PLR0913
    *,
    row: Any,
    targets: Iterable[ObjectDB],
    is_team_lane_row: bool,
    eff_intensity: int,
    success_level: int,
    dest_id: int | None,
    pos_a_id: int | None,
    pos_b_id: int | None,
) -> list[BulkConditionApplication]:
    """Build BulkConditionApplication objects for one applied-condition row.

    Computes severity and duration per target, using the team-lane pricing path
    or the row's own formula depending on *is_team_lane_row*.

    Args:
        row: An applied-condition row (TechniqueAppliedCondition or compatible
            abstract-base instance) carrying ``condition``, ``compute_severity``,
            ``compute_duration_rounds``, and ``stack_count``.
        targets: Iterable of ``ObjectDB`` targets to apply the condition to.
        is_team_lane_row: Whether this row's condition rides the bounded
            team-damage-percent lane (uses ``priced_percent_severity`` instead of
            the row's authored severity formula).
        eff_intensity: The effective intensity from the cast.
        success_level: The check success level from the cast.
        dest_id: Cast-time destination position FK, or ``None``.
        pos_a_id: Cast-time position-A FK, or ``None``.
        pos_b_id: Cast-time position-B FK, or ``None``.

    Returns:
        List of ``BulkConditionApplication`` objects, one per target.
    """
    from world.conditions.services import priced_percent_severity  # noqa: PLC0415

    applications: list[BulkConditionApplication] = []
    for target in targets:
        if is_team_lane_row:
            severity = priced_percent_severity(eff_intensity=eff_intensity, target=target)
        else:
            severity = row.compute_severity(
                effective_power=eff_intensity,
                success_level=success_level,
            )
        duration = row.compute_duration_rounds(
            effective_power=eff_intensity,
            success_level=success_level,
        )
        applications.append(
            BulkConditionApplication(
                target=target,
                template=row.condition,
                severity=severity,
                duration_rounds=duration,
                stack_count=row.stack_count,
                cast_destination_id=dest_id,
                cast_position_a_id=pos_a_id,
                cast_position_b_id=pos_b_id,
            )
        )
    return applications


def apply_technique_conditions(  # noqa: PLR0913 - cohesive condition-application params
    *,
    technique: Technique,
    success_level: int,
    eff_intensity: int,
    targets_by_kind: dict[str, list[ObjectDB]],  # noqa: OBJECTDB_PARAM
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
    applied_condition_rows: Iterable | None = None,
    position_params: dict[str, int] | None = None,
    soulfray_consented: bool = False,
) -> list[AppliedConditionResult]:
    """Apply authored applied-condition rows to pre-resolved targets.

    Iterates the applied-condition rows, skips rows whose ``minimum_success_level``
    exceeds *success_level*, and for each row applies the condition to every
    ``ObjectDB`` in ``targets_by_kind.get(row.target_kind, [])``.

    Severity and duration are computed via the row's formula methods using
    *eff_intensity* and *success_level* — EXCEPT for a row whose condition carries a
    team_damage_percent ``ConditionModifierEffect(scales_with_severity=True)``
    (#2643): that row's severity is instead computed per-target by
    ``world.conditions.services.priced_percent_severity``, priced against the
    landing target's level (works for either an ally-buff or an enemy-debuff — both
    ride the same bounded lane, see ``_apply_power_multiplier_stage``). The full
    batch is handed to ``bulk_apply_conditions`` in a single call and the results
    are mapped to ``AppliedConditionResult`` instances.

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
        soulfray_consented: The caster's consent, at cast time, to keep this batch's
            reactive cost and upkeep firing past zero anima at the price of Soulfray
            (#3573). Forwarded to ``bulk_apply_conditions`` and stamped onto every
            created ``ConditionInstance``.

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

    # #2019/#2206: cast-time position FKs, stamped onto each BulkConditionApplication
    # so bulk_apply_conditions can set them on the created ConditionInstance BEFORE
    # emitting CONDITION_APPLIED — same-event reactive handlers (create_obstacle_on_
    # condition and siblings) read these off payload.instance synchronously, so
    # patching them on AFTER bulk_apply_conditions returns would be too late.
    dest_id = (position_params or {}).get("destination_position_id")
    pos_a_id = (position_params or {}).get("position_a_id")
    pos_b_id = (position_params or {}).get("position_b_id")

    from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415
    from world.mechanics.constants import TEAM_DAMAGE_PERCENT_TARGET_NAME  # noqa: PLC0415

    bulk_applications: list[BulkConditionApplication] = []
    for row in rows:
        if success_level < row.minimum_success_level:
            continue
        # #2643: the bounded team-damage-percent lane prices its severity from
        # eff_intensity + the buffed/debuffed target's level, instead of the row's
        # own authored severity formula — checked once per row (not per target).
        is_team_lane_row = ConditionModifierEffect.objects.filter(
            condition=row.condition,
            modifier_target__name=TEAM_DAMAGE_PERCENT_TARGET_NAME,
            scales_with_severity=True,
        ).exists()
        targets = targets_by_kind.get(row.target_kind, [])
        bulk_applications.extend(
            _build_bulk_applications_for_row(
                row=row,
                targets=targets,
                is_team_lane_row=is_team_lane_row,
                eff_intensity=eff_intensity,
                success_level=success_level,
                dest_id=dest_id,
                pos_a_id=pos_a_id,
                pos_b_id=pos_b_id,
            )
        )

    if not bulk_applications:
        return []

    bulk_results = bulk_apply_conditions(
        bulk_applications,
        source_character=source_character,
        source_technique=technique,
        soulfray_consented=soulfray_consented,
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


def remove_technique_conditions(
    *,
    technique: Technique,
    success_level: int,
    eff_intensity: int,
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
         ``perform_check_with_modifiers(source_character, cure_check_type,
         cure_difficulty)``. Removal
         succeeds iff ``check_result.success_level > 0``; otherwise it is resisted (no-op
         for that target, cast continues). When ``cure_check_type`` is null, removal
         proceeds unconditionally (uncontested dispel).

    Delegates to :func:`world.conditions.services.remove_condition`, which handles
    stack decrement (``remove_all_stacks=False``), ``CONDITION_REMOVED`` emission,
    deferred-death resolution, and stories re-evaluation.

    Args:
        technique: The ``Technique`` whose ``removed_conditions`` rows are iterated.
        success_level: The cast technique's check success level (SL).
        eff_intensity: The effective intensity (injected power + pull bumps). Multiplied
            by ``row.cure_power_multiplier`` and added as ``extra_modifiers`` to the
            opposed cure check (Gate 3). Zero effect when the row's multiplier is 0
            (the default for every existing row) — exact back-compat.
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
                cure_power_multiplier=row.cure_power_multiplier,
                eff_intensity=eff_intensity,
            )
            for target in targets
        )
    return out


def _attempt_removal(  # noqa: PLR0913 - cohesive removal-attempt params
    *,
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    condition: Any,
    remove_all_stacks: bool,
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
    cure_power_multiplier: Any,
    eff_intensity: int,
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

    # Gate 3: opposed cure check (only when the condition defines one). Power scaling
    # (#3391) only ever helps here — cure_power_multiplier=0 (every row's default)
    # yields power_bonus=0, extra_modifiers=0, byte-identical to pre-#3391 behavior.
    cure_check_type = condition.cure_check_type
    if cure_check_type is not None:
        power_bonus = int(cure_power_multiplier * eff_intensity)
        check_result = perform_check_with_modifiers(
            source_character,
            cure_check_type,
            condition.cure_difficulty,
            extra_modifiers=power_bonus,
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


def apply_technique_treatments(  # noqa: PLR0913 - cohesive condition-application params
    *,
    technique: Technique,
    success_level: int,
    eff_intensity: int,
    targets_by_kind: dict[str, list[ObjectDB]],  # noqa: OBJECTDB_PARAM
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
    scene: Scene,
) -> list:
    """Perform technique-authored treatments on pre-resolved targets.

    Iterates all ``TechniqueTreatment`` rows on *technique*, skips rows whose
    ``minimum_success_level`` exceeds *success_level*, and for each row attempts
    ``perform_treatment`` on each target in
    ``targets_by_kind.get(row.target_kind, [])`` that carries the treatment's
    target condition.

    For each target:
      1. Finds the matching ``ConditionInstance`` / ``PendingAlteration`` via
         ``_condition_matches_treatment`` (handles PRIMARY, AFTERMATH, and
         PENDING_ALTERATION kinds — same helper the consent flow uses).
      2. If the treatment ``requires_bond``, resolves the caster's bond thread
         anchored to the target via ``_find_bond_thread``. If no bond thread
         is found, skips (no-op).
      3. Calls ``perform_treatment`` with ``skip_engagement_gate=True``.
      4. Catches ``TreatmentError`` subclasses — a treatment no-op does not
         abort the cast.

    Args:
        technique: The ``Technique`` whose ``treatments`` rows are iterated.
        success_level: The cast technique's check success level (SL).
        eff_intensity: The effective intensity (injected power + pull bumps). Forwarded
            to ``perform_treatment`` as ``power_intensity``, scaling the mend amount via
            ``treatment.mend_intensity_multiplier`` (0 by default — no effect).
        targets_by_kind: Mapping from ``ConditionTargetKind`` value (str) to
            resolved ``ObjectDB`` targets. Callers build this before calling.
        source_character: The caster's ``ObjectDB``, used as the treatment helper.
        scene: The active ``Scene``.

    Returns:
        List of ``TreatmentOutcome`` for successful treatments. Empty when no
        rows pass the SL gate or no targets carry matching conditions.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415

    rows = list(technique.treatments.select_related("treatment_template").all())
    if not rows:
        return []

    caster_sheet = CharacterSheet.objects.get(character=source_character)

    # Pre-fetch the caster's threads for bond resolution (mirrors
    # get_treatment_candidates' candidate_threads pattern).
    candidate_threads = list(Thread.objects.filter(owner=caster_sheet, retired_at__isnull=True))

    results: list = []
    for row in rows:
        if success_level < row.minimum_success_level:
            continue
        treatment = row.treatment_template
        targets = targets_by_kind.get(row.target_kind, [])
        for target in targets:
            target_sheet = CharacterSheet.objects.get(character=target)

            target_effect = _find_treatment_target_effect(treatment, target, target_sheet)
            if target_effect is None:
                continue

            bond_thread = _resolve_treatment_bond_thread(
                treatment, target, target_sheet, candidate_threads
            )
            if bond_thread is _BOND_NOT_FOUND:
                continue

            outcome = _perform_treatment_for_target(
                treatment=treatment,
                target=target,
                caster_sheet=caster_sheet,
                target_sheet=target_sheet,
                scene=scene,
                target_effect=target_effect,
                bond_thread=bond_thread,
                power_intensity=eff_intensity,
            )
            if outcome is not None:
                results.append(outcome)

    return results


def _find_treatment_target_effect(treatment: Any, target: Any, target_sheet: Any) -> Any:
    """Find the matching effect instance on the target for a treatment.

    Handles the PENDING_ALTERATION kind (queries ``PendingAlteration``) and
    the PRIMARY/AFTERMATH kinds (scans unresolved ``ConditionInstance`` rows
    via ``_condition_matches_treatment``).

    Args:
        treatment: The ``TechniqueTreatment`` template whose target_kind drives
            the lookup.
        target: The ``ObjectDB`` target object.
        target_sheet: The target's ``CharacterSheet``.

    Returns:
        The matching ``ConditionInstance`` or ``PendingAlteration``, or ``None``
        if no match is found.
    """
    from world.conditions.constants import TreatmentTargetKind  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.conditions.services import _condition_matches_treatment  # noqa: PLC0415
    from world.magic.constants import PendingAlterationStatus  # noqa: PLC0415
    from world.magic.models import PendingAlteration  # noqa: PLC0415

    if treatment.target_kind == TreatmentTargetKind.PENDING_ALTERATION:
        return PendingAlteration.objects.filter(
            character=target_sheet,
            status=PendingAlterationStatus.OPEN,
        ).first()

    instances = ConditionInstance.objects.filter(
        target=target,
        resolved_at__isnull=True,
    ).select_related("condition")
    for inst in instances:
        if _condition_matches_treatment(treatment, inst):
            return inst
    return None


# Sentinel for "bond required but not found" — distinct from ``None`` (no bond
# required) so the caller can distinguish "skip this target" from "proceed
# without a bond".
_BOND_NOT_FOUND = object()


def _resolve_treatment_bond_thread(
    treatment: Any, target: Any, target_sheet: Any, candidate_threads: Any
) -> Any:
    """Resolve the caster's bond thread for a treatment target if required.

    Args:
        treatment: The ``TechniqueTreatment`` template (may set ``requires_bond``).
        target: The ``ObjectDB`` target (used for debug logging only).
        target_sheet: The target's ``CharacterSheet``.
        candidate_threads: Pre-fetched list of the caster's active ``Thread`` rows.

    Returns:
        The resolved bond ``Thread``, ``None`` if no bond is required, or
        ``_BOND_NOT_FOUND`` if a bond is required but none was found.
    """
    from world.conditions.services import _find_bond_thread  # noqa: PLC0415

    if not treatment.requires_bond:
        return None
    bond_thread = _find_bond_thread(candidate_threads, target_sheet)
    if bond_thread is None:
        logger.debug(
            "Technique treatment %s skipped for target %s: no bond thread found.",
            treatment.name,
            target,
        )
        return _BOND_NOT_FOUND
    return bond_thread


def _perform_treatment_for_target(  # noqa: PLR0913
    *,
    treatment: Any,
    target: Any,
    caster_sheet: Any,
    target_sheet: Any,
    scene: Scene | None,
    target_effect: Any,
    bond_thread: Any,
    power_intensity: int = 0,
) -> Any:
    """Perform a single treatment on a target, catching ``TreatmentError``.

    Args:
        treatment: The ``TechniqueTreatment`` template to perform.
        target: The ``ObjectDB`` target (used for error logging).
        caster_sheet: The caster's ``CharacterSheet`` (treatment helper).
        target_sheet: The target's ``CharacterSheet``.
        scene: The active ``Scene``.
        target_effect: The matched ``ConditionInstance`` or ``PendingAlteration``.
        bond_thread: The resolved bond ``Thread``, or ``None`` if not required.
        power_intensity: The caster's effective intensity, forwarded to
            ``perform_treatment`` to scale the mend amount via
            ``treatment.mend_intensity_multiplier`` (default 0 — no effect).

    Returns:
        The ``TreatmentOutcome`` on success, or ``None`` if the treatment
        raised a ``TreatmentError`` (logged as a warning, no re-raise).
    """
    from world.conditions.exceptions import TreatmentError  # noqa: PLC0415
    from world.conditions.services import perform_treatment  # noqa: PLC0415

    try:
        return perform_treatment(
            helper_sheet=caster_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
            bond_thread=bond_thread,
            skip_engagement_gate=True,
            power_intensity=power_intensity,
        )
    except TreatmentError as exc:
        logger.warning(
            "Technique treatment %s failed for target %s: %s",
            treatment.name,
            target,
            exc,
        )
        return None
