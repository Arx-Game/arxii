"""Technique learning progress meter services (#2711).

contribute_to_technique_progress: the per-session training function. Spends
AP, adds meter-progress points, enforces the weekly cap, and mints the
CharacterTechnique when the meter fills.

is_cross_path_learning: the style-comparison helper used at meter creation
to determine whether the cross-path multiplier applies.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.exceptions import WeeklyTrainingCapExceeded
from world.magic.models import TechniqueProgress, TechniqueProgressWeekly
from world.magic.services.gift_acquisition import (
    get_gift_acquisition_config,
    magic_learning_ap_cost_surcharge_percent,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.game_clock.models import GameWeek
    from world.roster.models import RosterTenure


def is_cross_path_learning(
    teacher_tenure: RosterTenure | None,
    learner_sheet: CharacterSheet,
) -> bool:
    """Whether the teacher's Path.style differs from the learner's (#2711).

    Returns True only when both teacher and learner have a non-null
    ``Path.style`` and they differ. Fail-open: null style on either side,
    or no teacher, → False. Mirrors ADR-0164's philosophy and the existing
    ``magic_learning_ap_cost_surcharge_percent`` defensive-tolerance convention.
    """
    if teacher_tenure is None:
        return False

    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    teacher_path = current_path_for_character(teacher_tenure.character)
    learner_path = current_path_for_character(learner_sheet.character)

    if teacher_path is None or learner_path is None:
        return False

    if teacher_path.style_id is None or learner_path.style_id is None:
        return False

    return teacher_path.style_id != learner_path.style_id


@transaction.atomic
def contribute_to_technique_progress(
    sheet: CharacterSheet,
    progress: TechniqueProgress,
    dev_points: int,
    *,
    ap_to_spend: int | None = None,
    game_week: GameWeek | None = None,
):
    """Invest AP toward an in-progress technique meter (#2711, #2727).

    Spends AP (with the Unbound surcharge applied), adds meter-progress
    points, enforces the weekly cap, and mints the CharacterTechnique when
    the meter fills.

    Args:
        sheet: The learner's CharacterSheet.
        progress: The TechniqueProgress meter to contribute toward.
        dev_points: Meter-progress points (dev points) to contribute.
        ap_to_spend: AP to charge (with surcharge). When None (default),
            derived from dev_points (original #2711 behavior). When set,
            decouples AP cost from dev-point yield — the check-based training
            wrapper (#2727) uses this so a botch spends full AP but credits
            0 dev points.
        game_week: Optional GameWeek; resolved from the current game week
            if not provided.

    Returns:
        The minted CharacterTechnique if the meter filled, None otherwise.

    Raises:
        WeeklyTrainingCapExceeded: If the weekly cap is already reached.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.magic.exceptions import MagicError  # noqa: PLC0415
    from world.magic.services.technique_acquisition import learn_technique  # noqa: PLC0415

    if game_week is None:
        game_week = get_current_game_week()

    config = get_gift_acquisition_config()

    # 1. Compute effective weekly cap.
    if progress.is_cross_path and config.cross_path_cap_divisor > 1:
        effective_cap = config.weekly_training_cap // config.cross_path_cap_divisor
    else:
        effective_cap = config.weekly_training_cap

    # 2. Get-or-create the weekly tracker.
    weekly, _created = TechniqueProgressWeekly.objects.select_for_update().get_or_create(
        character_sheet=sheet,
        technique=progress.technique,
        game_week=game_week,
        defaults={"points_contributed": 0},
    )

    # 3. Check weekly cap.
    if weekly.points_contributed >= effective_cap:
        msg = f"You've trained as much as you can this week ({effective_cap} points)."
        raise WeeklyTrainingCapExceeded(msg)

    # 4. Clamp the dev-point contribution to remaining weekly allowance.
    clamped = min(dev_points, effective_cap - weekly.points_contributed)

    # 5. Compute AP to spend (with Unbound surcharge).
    if ap_to_spend is None:
        ap_base = clamped
    else:
        ap_base = ap_to_spend
    surcharge_percent = magic_learning_ap_cost_surcharge_percent(sheet)
    ap_to_spend_actual = math.ceil(ap_base * (100 + surcharge_percent) / 100)

    # 6. Spend AP.
    pool = ActionPointPool.get_or_create_for_character(sheet.character)
    if not pool.can_afford(ap_to_spend_actual):
        msg = f"Insufficient action points (need {ap_to_spend_actual}, have {pool.current})."
        raise MagicError(msg)
    pool.spend(ap_to_spend_actual)

    # 7. Add to meter (atomic).
    progress = TechniqueProgress.objects.select_for_update().get(pk=progress.pk)
    progress.points_accumulated += clamped
    progress.save(update_fields=["points_accumulated", "updated_at"])

    # 8. Update weekly tracker.
    weekly.points_contributed += clamped
    weekly.save(update_fields=["points_contributed"])

    # 9. Check completion.
    if progress.points_accumulated >= progress.total_required:
        ct = learn_technique(
            sheet,
            progress.technique,
            source=progress.source,
            ap_cost=0,
        )
        progress.delete()
        return ct

    return None
