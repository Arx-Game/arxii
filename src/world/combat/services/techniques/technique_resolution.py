"""Resolving a combat technique and building its result."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.services.damage.vulnerability import _vulnerability_intensity_bonus
from world.combat.services.techniques.intensity import _sum_active_flat_bonuses
from world.combat.services.techniques.technique_resolver import CombatTechniqueResolver
from world.combat.services.techniques.technique_targets import (
    _build_affected_targets,
    _check_combat_target_prerequisites,
    _resolve_primary_target_sheet,
)
from world.combat.types import CombatTechniqueResolution, CombatTechniqueResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.checks.types import CheckResult
    from world.magic.models import FuryTier
    from world.magic.types import CastCheck, TechniqueUseResult

    PerformCheckFn = Callable[..., CheckResult]


def _build_combat_result(
    technique_use_result: TechniqueUseResult,
    resolver: CombatTechniqueResolver,  # noqa: ARG001 - kept for future extensibility
    fury_committed: FuryTier | None = None,
) -> CombatTechniqueResult:
    """Translate use_technique's outcome into the adapter's return shape."""
    if not technique_use_result.confirmed:
        return CombatTechniqueResult(
            damage_results=[],
            applied_conditions=[],
            technique_use_result=technique_use_result,
            fury_committed=fury_committed,
        )

    resolution = technique_use_result.resolution_result
    # Defensive assertion against programmer error — service contract
    # is that combat resolvers return CombatTechniqueResolution.
    if not isinstance(resolution, CombatTechniqueResolution):
        msg = f"Expected CombatTechniqueResolution, got {type(resolution).__name__}"
        raise TypeError(msg)

    return CombatTechniqueResult(
        damage_results=list(resolution.damage_results),
        applied_conditions=list(resolution.applied_conditions),
        technique_use_result=technique_use_result,
        power_ledger=resolution.power_ledger,
        fury_committed=fury_committed,
        removed_conditions=list(resolution.removed_conditions),
    )


def resolve_combat_technique(
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    fatigue_category: str,
    cast_check: CastCheck,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Route a damage-path combat technique through use_technique.

    Builds a CombatTechniqueResolver and passes it to use_technique as
    resolve_fn. The magic envelope handles anima, soulfray, mishap,
    PRE_CAST/CAST events, reactive scar interception, and corruption.
    The resolver does the offense check + damage application inside
    that envelope.

    ``cast_check`` is the caster's resolved cast: the check type the offense roll uses and
    the skill terms (the technique skill) it adds (#4450).

    Soulfray warning is auto-confirmed at round resolution time —
    frontend handles preview before submission.

    TECHNIQUE_AFFECTED fires per target via _build_affected_targets:
    opponent target → opp.objectdb; ally target → ally character ObjectDB.

    Other pull effect kinds are deferred:
    - INTENSITY_BUMP: needs runtime stats to accept combat context
    - CAPABILITY_GRANT: tied to non-attack pipeline
    - NARRATIVE_ONLY: cosmetic surfacing
    - VITAL_BONUS: already wired through recompute_max_health_with_threads
    """
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.fury import run_fury_for_action  # noqa: PLC0415

    encounter = participant.encounter
    pull_flat_bonus = _sum_active_flat_bonuses(participant, encounter)

    resolver = CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=pull_flat_bonus,
        fatigue_category=fatigue_category,
        offense_check_type=cast_check.check_type,
        offense_check_fn=offense_check_fn,
        offense_extra_traits=cast_check.extra_traits,
    )

    targets = _build_affected_targets(participant, action)
    _check_combat_target_prerequisites(
        action.focused_action, participant.character_sheet.character, targets
    )

    fury_res = run_fury_for_action(
        character=participant.character_sheet.character,
        fury_commitment=action.fury_commitment,
        fury_anchor=action.fury_anchor,
        source_technique=action.focused_action,
    )

    # Signature-motif bonus (#1582): a flat intensity delta on the signed technique's
    # thread folds into power derivation, exactly as in the standalone cast path
    # (no-op / 0 when unsigned).
    from world.magic.services.signature_effects import signature_intensity_delta  # noqa: PLC0415

    sig_intensity_delta = signature_intensity_delta(
        participant.character_sheet.character, action.focused_action
    )

    technique_use_result = use_technique(
        character=participant.character_sheet.character,
        technique=action.focused_action,
        resolve_fn=resolver,
        confirm_soulfray_risk=action.confirm_soulfray_risk,
        strain_commitment=action.strain_commitment,
        targets=targets,
        lethal=encounter.is_lethal,
        control_penalty=fury_res.control_penalty if fury_res else 0,
        power_intensity_bonus=(
            (fury_res.intensity_bonus if fury_res else 0)
            + sig_intensity_delta
            + _vulnerability_intensity_bonus(action)
        ),
        # #2536 Task 4: thread the live round context so situational-perk
        # POWER_BONUS providers can read combat-positioning situations
        # (AT_RANGE/IN_MELEE/SURROUNDED/...). Cheap to build — CombatRoundContext
        # just wraps the already-resolved participant (its encounter rides the
        # SharedMemoryModel identity map), no extra query.
        situation_ctx=CombatRoundContext(participant),
        # #2536 Task 4 review fix: thread the cast's primary target's
        # CharacterSheet so target-keyed situational-perk POWER_BONUS
        # providers (TARGET_DISTRACTED/TARGET_SWAYED_BY_ALLY/
        # TARGET_FOCUSED_ELSEWHERE/TARGET_FAVORABLY_DISPOSED) can fire.
        target_sheet=_resolve_primary_target_sheet(action),
    )

    return _build_combat_result(
        technique_use_result, resolver, fury_committed=fury_res.realized_tier if fury_res else None
    )
