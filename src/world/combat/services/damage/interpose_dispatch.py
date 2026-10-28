"""Dispatching interposes and grading their outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flows.events.payloads import DamagePreApplyPayload
from world.combat import services as _svc
from world.combat.models import CombatRoundAction
from world.magic.models.soulfray import SoulfrayConfig
from world.magic.services.anima import deduct_anima
from world.mechanics.types import ChallengeResolutionResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult
    from world.magic.models import Technique
    from world.magic.models.anima import CharacterAnima


def _narrate_reaction_declined(
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: object,
) -> None:
    """Tell a guardian, privately, that enough hands already answered this blow (#3574).

    ``ABSORPTION_CAP_PER_MOMENT`` interceptors already answered this payload. Guarding
    has no per-round cap since #4676 (each reaction makes the next roll harder instead).
    No room line: ADR-0161 chose a silent no-op so the table never learns a guardian's
    state, and this keeps that while the guardian stops guessing. ``protected`` is
    whatever the fire seam holds and is only ever stringified.
    """
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    narrate_privately(
        interposer,
        f"Enough hands have already answered that blow; your guard over {protected} stays down.",
    )


def _settle_technique_interpose_cost(  # noqa: PLR0913 - debit + accrue needs all of it
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    anima: CharacterAnima,
    cost: int,
    consented: bool,
    check_result: CheckResult | None,
) -> None:
    """Debit a firing technique guardian's anima and, if consented, accrue Soulfray.

    Split out of :func:`_try_technique_interpose` (#3573) purely to keep that
    function's branch count under the complexity budget - the debit-then-accrue
    sequencing is otherwise a single linear step in that function's flow.
    """
    encounter = action.participant.encounter
    deficit = deduct_anima(interposer, cost, lethal=encounter.is_lethal)
    if not consented:
        return
    _svc.accumulate_soulfray(
        character=interposer,
        anima=anima,
        deficit=deficit,
        soulfray_config=SoulfrayConfig.objects.cached_singleton(),
        check_result=check_result,
        lethal=encounter.is_lethal,
    )
    if deficit > 0:
        ally_name = (
            str(action.focused_ally_target.character_sheet.character)
            if action.focused_ally_target_id
            else str(protected)
        )
        _svc._broadcast_commitment_line(  # noqa: SLF001 (test patch seam)
            encounter,
            f"{interposer} tears at their own soul to hold the line over {ally_name}!",
        )


def _narrate_technique_interpose_fizzle(
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
) -> None:
    """Tell the guardian, then the room, that an unpaid protective technique fizzled (#3574).

    Private line carries the why (anima); the room line never carries a number.
    The mechanical no-op shape is unchanged: no roll, no charge, damage proceeds.
    """
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        technique_display_name,
    )
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    display_name = technique_display_name(interposer, technique)
    narrate_privately(
        interposer,
        f"Your {display_name} gutters for want of anima; {protected} takes the blow unguarded.",
    )
    _svc._broadcast_commitment_line(  # noqa: SLF001 (test patch seam)
        action.participant.encounter,
        f"{interposer} reaches to shield {protected}, and the working fails to catch.",
    )


def _grade_interpose_damage(
    pre_payload: DamagePreApplyPayload,
    success_level: int,
    *,
    interposer: object | None = None,
    force_clean: bool = False,
) -> bool:
    """Shared clean/partial/fail damage banding for BOTH interpose paths (#2207).

    Extracted from :func:`apply_interpose_outcome` (the mundane
    capability-reaction path) so :func:`_try_technique_interpose` (a technique
    guardian's own cast-check resolution) grades identically without
    duplicating the covenant-role-scaling partial-block math:

    - **clean block** (``force_clean`` or ``success_level > 0``): the blow is
      fully turned aside — ``pre_payload.amount = 0``.
    - **partial** (``success_level == 0``, not forced-clean): the interposer
      softens but does not stop the blow — ``pre_payload.amount //= 2``. An
      interposer engaged in a role with a ``combat_interpose`` scaling row
      scales this reduction by their COVENANT_ROLE thread level (#2022,
      #2529): the deeper the vow, the more damage the partial block absorbs.
    - **failure** (``success_level < 0``): the interpose fails — no change.

    ``force_clean`` lets a caller fold in a resolution-type override (the
    mundane path's ``ChallengeResolutionResult.resolution_type == DESTROY``)
    without leaking that concept into this shared helper's contract.

    Returns ``True`` when this graded as a clean block — the technique path
    uses this to gate BLINK ward relocation (clean success only).
    """
    is_clean_block = force_clean or success_level > 0

    if is_clean_block:
        pre_payload.amount = 0
        return True

    if success_level == 0:
        # #2022/#2529: covenant-role scaling — a deeper vow blocks more damage
        # on a partial block. The bonus reduces the remaining damage further.
        divisor = 2
        if interposer is not None:
            from world.covenants.constants import CovenantScaledAction  # noqa: PLC0415
            from world.covenants.services import (  # noqa: PLC0415
                covenant_role_action_scaling_bonus,
            )

            bonus = covenant_role_action_scaling_bonus(interposer, CovenantScaledAction.INTERPOSE)
            if bonus > 0:
                # Scale: partial block reduces to amount / (2 + bonus).
                # A bonus of 1.0 (a deep SHIELD vow) makes the divisor 3,
                # blocking 67% instead of 50%.
                divisor = int(2 + bonus)
        pre_payload.amount //= divisor
        return False

    # Failure (success_level < 0) — the blow continues at full damage.
    return False


def apply_interpose_outcome(
    pre_payload: DamagePreApplyPayload,
    result: ChallengeResolutionResult,
    *,
    interposer: object | None = None,
) -> None:
    """Map a graded interpose resolution onto *pre_payload*.

    Mirrors :func:`~world.areas.positioning.plummet.resolve_catch`'s graded
    branches but acts on the incoming damage amount rather than plummet state.
    Delegates the clean/partial/fail banding to :func:`_grade_interpose_damage`
    (shared with the technique-guardian path, #2207) — this wrapper's only job
    is converting a ``ChallengeResolutionResult`` into the ``(success_level,
    force_clean)`` pair that helper expects: ``resolution_type == DESTROY``
    forces a clean block even at ``success_level <= 0`` (a capability-authored
    instant stop).
    """
    from world.mechanics.constants import ResolutionType  # noqa: PLC0415

    check_result = result.check_result
    success_level = check_result.success_level if check_result is not None else 0
    force_clean = result.resolution_type == ResolutionType.DESTROY

    _grade_interpose_damage(
        pre_payload, success_level, interposer=interposer, force_clean=force_clean
    )
