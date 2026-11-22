"""Check-based technique training service (#2727).

resolve_training_check: resolves a learning check, maps the outcome to a
dev-point multiplier via TrainingOutcomeAward, and calls
contribute_to_technique_progress with decoupled AP-spend.
"""

from __future__ import annotations

from decimal import Decimal
import math
from typing import TYPE_CHECKING

from world.achievements.constants import AccessChangeSource
from world.checks.constants import ModifierSourceKind
from world.checks.services import (
    compute_check_rating,
    difficulty_step_points,
    perform_check_with_modifiers,
)
from world.checks.types import ModifierContribution
from world.magic.models import TrainingOutcomeAward
from world.magic.services.gift_acquisition import get_gift_acquisition_config
from world.magic.services.magic_skills import technique_learning_terms
from world.magic.services.technique_progress import contribute_to_technique_progress
from world.magic.types.training import TrainingCheckResult
from world.progression.services.skill_development import get_character_path_level

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import TechniqueProgress
    from world.roster.models import RosterTenure

# Name of the seeded CheckType for technique training.
TECHNIQUE_TRAINING_CHECK_TYPE_NAME = "Technique Training"

# How the Academy trainer's instruction reads in a roll's breakdown (#2741).
ACADEMY_INSTRUCTION_LABEL = "Academy instruction"


def is_academy_instructed(progress: TechniqueProgress) -> bool:
    """Whether ``progress`` is a meter an Academy trainer's offer opened (#2741).

    That trainer is never present at a session, so the meter itself says the learner
    paid for instruction: it lifts the self-study penalty and carries the offer's
    ``instruction_bonus``, which is read from the row so it holds after a restart.
    """
    return progress.source == AccessChangeSource.ACADEMY_TRAINING


def resolve_training_check(
    learner: CharacterSheet,
    progress: TechniqueProgress,
    *,
    ap_to_invest: int,
    teacher: RosterTenure | None = None,
) -> TrainingCheckResult:
    """Resolve a learning check and contribute dev points (#2727).

    Wraps contribute_to_technique_progress with a check that scales dev-point
    yield by outcome. AP is always spent (ap_to_invest); only the dev-point
    yield varies.

    Args:
        learner: The learner's CharacterSheet.
        progress: The TechniqueProgress meter to contribute toward.
        ap_to_invest: Base AP the learner wants to invest this session.
        teacher: The teacher's RosterTenure (None when no player teacher is present).
            With none, a meter an Academy offer opened is paid instruction (no self-study
            penalty, plus the meter's ``instruction_bonus``); any other meter is self-study.

    Returns:
        TrainingCheckResult with the outcome, multiplier, dev points, and
        the minted CharacterTechnique if the meter filled.

    Raises:
        TechniqueTrainingNotConfigured: If the "Technique Training" CheckType has
            not been authored (content tracked in ArxII-lore#72).
        WeeklyTrainingCapExceeded: If the weekly cap is reached (from the seam).
        MagicError: If the learner can't afford the AP (from the seam).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.magic.exceptions import TechniqueTrainingNotConfigured  # noqa: PLC0415

    config = get_gift_acquisition_config()
    technique = progress.technique

    # 1. Resolve the check type. No silent fallback (#3043) — an arbitrary
    # unrelated CheckType rolled in place of training is worse than a loud,
    # named failure naming the missing content row.
    try:
        check_type = CheckType.objects.get(name=TECHNIQUE_TRAINING_CHECK_TYPE_NAME)
    except CheckType.DoesNotExist as exc:
        raise TechniqueTrainingNotConfigured from exc

    # 2. Compute target_difficulty from the three drivers.
    learner_level = get_character_path_level(learner.character) or 0
    target_difficulty = difficulty_step_points(
        technique.tier * config.training_tier_difficulty_step_tenths, learner_level
    )

    target_difficulty -= learner_level // config.training_level_divisor

    learning_terms = technique_learning_terms(learner.character, technique, check_type)
    instruction: list[ModifierContribution] = []
    if teacher is not None and teacher.character is not None:
        teacher_rating = compute_check_rating(
            teacher.character, check_type, extra_traits=learning_terms
        )
        teacher_skill_bonus = teacher_rating // config.training_teacher_skill_divisor
    elif is_academy_instructed(progress):
        # Paid instruction: no self-study penalty, and the offer's bonus joins the roll
        # through the modifier seam so the breakdown names it.
        teacher_skill_bonus = 0
        if progress.instruction_bonus > 0:
            instruction.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.CHARACTER,
                    source_label=ACADEMY_INSTRUCTION_LABEL,
                    value=progress.instruction_bonus,
                )
            )
    else:
        teacher_skill_bonus = 0
        target_difficulty += difficulty_step_points(
            config.training_self_study_difficulty_penalty_tenths, learner_level
        )

    target_difficulty = max(0, target_difficulty - teacher_skill_bonus)

    # 3. Resolve the check.
    check_result = perform_check_with_modifiers(
        learner.character,
        check_type,
        target_difficulty=target_difficulty,
        extra_traits=learning_terms,
        extra_contributions=instruction,
    )

    # 4. Map outcome to dev-point multiplier.
    if check_result.outcome is not None:
        try:
            award = TrainingOutcomeAward.objects.get(outcome_tier=check_result.outcome)
            multiplier = award.dev_point_multiplier
        except TrainingOutcomeAward.DoesNotExist:
            multiplier = Decimal(0)
    else:
        multiplier = Decimal(0)

    # 5. Compute dev points (scaled) and AP (always full).
    dev_points = math.floor(Decimal(str(ap_to_invest)) * multiplier)

    # 6. Contribute via the seam.
    technique_acquired = contribute_to_technique_progress(
        learner,
        progress,
        dev_points,
        ap_to_spend=ap_to_invest,
    )

    return TrainingCheckResult(
        outcome_name=check_result.outcome_name,
        success_level=check_result.success_level,
        dev_point_multiplier=multiplier,
        dev_points_contributed=dev_points,
        ap_spent=ap_to_invest,
        technique_acquired=technique_acquired,
    )
