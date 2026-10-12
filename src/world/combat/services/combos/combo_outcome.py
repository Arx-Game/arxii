"""Processing combo outcomes and riders."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import F, Sum

from world.combat import services as _svc
from world.combat.constants import (
    DEFENSE_CRITICAL_MULTIPLIER,
    DEFENSE_FULL_MULTIPLIER,
    DEFENSE_NO_DAMAGE_THRESHOLD,
    DEFENSE_REDUCED_MULTIPLIER,
    DEFENSE_REDUCED_THRESHOLD,
    OpponentStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
)
from world.combat.types import ActionOutcome

# ---------------------------------------------------------------------------
# Combo post-resolution: fused narration + discovery + use-count
# ---------------------------------------------------------------------------


def _group_combo_outcomes(
    action_outcomes: list[ActionOutcome],
) -> dict[int, list[tuple[ActionOutcome, CombatParticipant]]]:
    """Group ``action_outcomes`` by ``combo_used``, resolving each participant.

    Extracted from ``_process_combo_outcomes`` (S3776) — same grouping pass,
    same behavior, just named on its own.
    """
    combo_groups: dict[int, list[tuple[ActionOutcome, CombatParticipant]]] = defaultdict(list)
    for outcome in action_outcomes:
        if outcome.combo_used is not None and outcome.participant_id is not None:
            participant = (
                CombatParticipant.objects.filter(pk=outcome.participant_id)
                .select_related("character_sheet__character")
                .first()
            )
            if participant is not None:
                combo_groups[outcome.combo_used.pk].append((outcome, participant))
    return combo_groups


def _broadcast_combo_finisher_narration(
    combo: ComboDefinition,
    group: list[tuple[ActionOutcome, CombatParticipant]],
    round_number: int,
    encounter: CombatEncounter,
) -> None:
    """Broadcast the joint finisher narration for one multi-contributor combo group.

    Extracted from ``_process_combo_outcomes`` (S3776) — same target-label
    lookup and narration/broadcast calls, same behavior, just named on its
    own.
    """
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_combo_finisher_narration,
    )
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    # Persona display name, not str(CombatParticipant) -> str(CharacterSheet)
    # ("Sheet for {key}") -- #4091 fix round 3.
    persona_names = persona_names_for_sheets(p.character_sheet_id for _, p in group)
    contributor_labels = [
        persona_names.get(p.character_sheet_id, p.character_sheet.character.key) for _, p in group
    ]
    total_damage = sum(dr.damage_dealt for outcome, _ in group for dr in outcome.damage_results)
    # Determine target label from the first outcome's action.
    target_label = None
    for _outcome, participant in group:
        action = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=round_number,
        ).first()
        if action and action.focused_opponent_target_id:
            target_label = action.focused_opponent_target.name
            break

    signature_clause = _signature_clause_for(combo)
    narration = render_combo_finisher_narration(
        combo_name=combo.name,
        contributor_labels=contributor_labels,
        target_label=target_label,
        total_damage=total_damage,
        signature_clause=signature_clause,
    )
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _process_combo_outcomes(
    action_outcomes: list[ActionOutcome],
    encounter: CombatEncounter,
    round_number: int,  # reserved for future round-scoped narration
) -> list[ActionOutcome]:
    """Post-resolution pass: group combo outcomes, fire narration + discovery.

    Called from ``resolve_round`` after ``_resolve_actions`` returns and
    before ``assess_break_bar``. For each distinct combo that fired:

    1. Broadcast a joint finisher narration naming all contributors (if ≥2).
    2. Fire the discovery ceremony for first-ever triggers.
    3. Increment each contributor's ``ComboLearning.use_count``.
    4. Check for signature flourish unlock.

    Single-contributor combos keep the existing per-PC narration (backward
    compatible — the per-PC ``_record_and_broadcast_pc_action`` already ran).
    """
    from world.combat.models import ComboLearning  # noqa: PLC0415

    # Group outcomes by combo_used.
    combo_groups = _group_combo_outcomes(action_outcomes)

    for group in combo_groups.values():
        combo = group[0][0].combo_used
        # _group_combo_outcomes only ever groups outcomes with combo_used set.
        assert combo is not None  # noqa: S101  # type narrowing for ty
        participant_sheets = [p.character_sheet for _, p in group]

        # 1. Joint finisher narration (only for multi-contributor combos).
        _MULTI_CONTRIBUTOR_THRESHOLD = 2
        if len(group) >= _MULTI_CONTRIBUTOR_THRESHOLD:
            _broadcast_combo_finisher_narration(combo, group, round_number, encounter)

        # 2. Fire discovery ceremony for first-ever triggers.
        was_known = ComboLearning.objects.filter(
            combo=combo,
            character_sheet__in=participant_sheets,
        ).exists()
        if not was_known and combo.discoverable_via_combat:
            from world.combat.combo_discovery import fire_combo_discovery  # noqa: PLC0415

            fire_combo_discovery(
                combo=combo,
                participant_sheets=participant_sheets,
                scene=encounter.scene,
            )

        # 3. Increment use_count for each contributor.
        for sheet in participant_sheets:
            ComboLearning.objects.filter(
                combo=combo,
                character_sheet=sheet,
            ).update_with_reason(
                reason="issue #3817: intentional atomic write",
                use_count=F("use_count") + 1,
            )

    return action_outcomes


def _signature_clause_for(
    combo: ComboDefinition,
) -> str | None:
    """Return the signature flourish clause if unlocked, else None.

    Checks for a ``ComboSignature`` row matching the combo. If one exists,
    sums ``use_count`` across covenant members who know the combo and checks
    against ``unlock_threshold``.
    """
    from world.combat.models import ComboSignature  # noqa: PLC0415

    signatures = ComboSignature.objects.filter(combo=combo).select_related("covenant")
    for sig in signatures:
        # Sum use_count across all covenant members who know this combo.
        total_uses = (
            ComboLearning.objects.filter(
                combo=combo,
                character_sheet__combat_participations__covenant_role__covenant=sig.covenant,
            ).aggregate(total=Sum("use_count"))["total"]
            or 0
        )

        if total_uses >= sig.unlock_threshold and sig.flourish_narrative:
            return sig.flourish_narrative

    return None


# ---------------------------------------------------------------------------
# Defensive check integration
# ---------------------------------------------------------------------------


def _damage_multiplier_for_success(success_level: int) -> float:
    """Map a check success_level to a damage multiplier.

    Args:
        success_level: The ``CheckResult.success_level`` value.

    Returns:
        Float multiplier applied to NPC base damage.
    """
    if success_level >= DEFENSE_NO_DAMAGE_THRESHOLD:
        return 0.0
    if success_level >= DEFENSE_REDUCED_THRESHOLD:
        return DEFENSE_REDUCED_MULTIPLIER
    if success_level <= -1:
        return DEFENSE_CRITICAL_MULTIPLIER
    return DEFENSE_FULL_MULTIPLIER


def _apply_combo_rider(
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent,
    outcome: ActionOutcome,
) -> None:
    """Append combo-upgraded bonus damage when the target is still alive.

    The combo rider is applied in addition to the pipeline result. It is
    skipped when the target has been defeated (by the pipeline or earlier).
    """
    target.refresh_from_db()
    if target.status == OpponentStatus.DEFEATED:
        return
    combo = action.combo_upgrade
    dmg_result = _svc.apply_damage_to_opponent(
        target,
        combo.bonus_damage,
        bypass_soak=combo.bypass_soak,
        source_sheet=participant.character_sheet,
    )
    outcome.combo_used = combo
    outcome.damage_results.append(dmg_result)
