"""Service functions for the skills training system."""

from __future__ import annotations

from collections import defaultdict
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Max, Sum

from world.action_points.models import ActionPointConfig, ActionPointPool
from world.classes.models import CharacterClassLevel
from world.progression.models.rewards import DevelopmentTransaction
from world.progression.types import DevelopmentSource, ProgressionReason
from world.relationships.helpers import get_relationship_tier
from world.roster.models import RosterEntry
from world.skills.models import (
    CharacterSkillValue,
    CharacterSpecializationValue,
    Skill,
    SkillPointBudget,
    Specialization,
    TrainingAllocation,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona

logger = logging.getLogger(__name__)

_UNSET = object()

# XP boundaries: skill values where advancement is blocked until XP purchase.
# Values ending in 9 within each decade represent mastery gates.
_XP_BOUNDARY_DIGIT = 9
_XP_BOUNDARY_MIN = 19
_XP_BOUNDARY_MAX = 49


def _get_path_level(character: ObjectDB) -> int:
    """Get the character's highest class level.

    Looks up all CharacterClassLevel rows for the character and returns the
    maximum ``level`` value. Defaults to 1 if the character has no class levels.

    Args:
        character: The character whose path level to look up.

    Returns:
        The highest class level, or 1 if none exist.
    """
    levels = character.character_class_levels.all()
    if not levels:
        return 1
    return max(entry.level for entry in levels)


def _bulk_path_levels(character_pks: set[int]) -> dict[int, int]:
    """Batch-fetch path levels for multiple characters in a single query.

    Args:
        character_pks: Set of character primary keys to look up.

    Returns:
        Dict mapping character PK to highest class level (default 1).
    """
    qs = (
        CharacterClassLevel.objects.filter(character_id__in=character_pks)
        .values("character_id")
        .annotate(max_level=Max("level"))
    )
    levels = {row["character_id"]: row["max_level"] for row in qs}
    return {pk: levels.get(pk, 1) for pk in character_pks}


def _get_skill_value(character: ObjectDB, skill: Skill) -> int:
    """Look up a character's value for a given skill.

    Args:
        character: The character to look up.
        skill: The skill to query.

    Returns:
        The raw skill value, or 0 if the character has no value for this skill.
    """
    try:
        return CharacterSkillValue.objects.get(character=character, skill=skill).value
    except CharacterSkillValue.DoesNotExist:
        return 0


def _get_spec_value(character: ObjectDB, specialization: Specialization) -> int:
    """Look up a character's value for a given specialization.

    Args:
        character: The character to look up.
        specialization: The specialization to query.

    Returns:
        The raw specialization value, or 0 if the character has no value for it.
    """
    try:
        return CharacterSpecializationValue.objects.get(
            character=character, specialization=specialization
        ).value
    except CharacterSpecializationValue.DoesNotExist:
        return 0


def _get_teaching_skill() -> Skill | None:
    """Look up the Teaching skill from the skill config.

    Returns:
        The Teaching Skill instance, or None if not configured.
    """
    budget = SkillPointBudget.get_active_budget()
    return budget.teaching_skill


def _get_teaching_value(
    mentor_character: ObjectDB,
    teaching_skill: Skill | None = _UNSET,  # type: ignore[assignment]
) -> int:
    """Look up the mentor's Teaching skill value.

    Args:
        mentor_character: The mentor character to look up.
        teaching_skill: Pre-fetched Teaching skill instance for batch use.
            Pass ``_UNSET`` (default) to look it up automatically.

    Returns:
        The mentor's Teaching skill value, or 0 if the Teaching skill does not
        exist or the mentor has no value for it.
    """
    if teaching_skill is _UNSET:
        teaching_skill = _get_teaching_skill()
    if teaching_skill is None:
        return 0
    return _get_skill_value(mentor_character, teaching_skill)


def calculate_training_development(
    allocation: TrainingAllocation,
    *,
    _teaching_skill: Skill | None = _UNSET,  # type: ignore[assignment]
    _path_levels: dict[int, int] | None = None,
) -> int:
    """Calculate development points earned from a training allocation.

    Formula::

        base_gain = 5 * AP_spent * path_level

        If mentor:
            mentor_skill_total = mentor_skill + teaching (+ parent if spec)
            student_skill_total = student_skill (+ parent if spec)
            ratio = mentor_skill_total / student_skill_total
            effective_AP = AP_spent + teaching
            mentor_bonus = effective_AP * ratio * (relationship_tier + 1)

        dev_points = base_gain + mentor_bonus

    Args:
        allocation: The TrainingAllocation record to calculate for.
        _teaching_skill: Pre-fetched Teaching skill for batch use (internal).
        _path_levels: Pre-built {character_pk: level} dict for batch use (internal).

    Returns:
        Development points as an integer (truncated).
    """
    character = allocation.character
    ap_spent = allocation.ap_amount

    if _path_levels is not None:
        path_level = _path_levels.get(character.pk, 1)
    else:
        path_level = _get_path_level(character)
    base_gain = 5 * ap_spent * path_level

    if not allocation.mentor:
        return int(base_gain)

    mentor_character = allocation.mentor.character
    teaching = _get_teaching_value(mentor_character, teaching_skill=_teaching_skill)

    if allocation.specialization:
        # Specialization training: include parent skill in totals
        spec = allocation.specialization
        parent_skill = spec.parent_skill

        student_parent = _get_skill_value(character, parent_skill)
        student_spec = _get_spec_value(character, spec)
        student_total = student_parent + student_spec

        mentor_parent = _get_skill_value(mentor_character, parent_skill)
        mentor_spec = _get_spec_value(mentor_character, spec)
        mentor_total = mentor_parent + mentor_spec + teaching
    else:
        # Skill training
        skill = allocation.skill
        student_total = _get_skill_value(character, skill)
        mentor_total = _get_skill_value(mentor_character, skill) + teaching

    # Prevent division by zero
    if student_total == 0:
        student_total = 1

    ratio = mentor_total / student_total
    effective_ap = ap_spent + teaching
    relationship_tier = get_relationship_tier(character, mentor_character)
    mentor_bonus = effective_ap * ratio * (relationship_tier + 1)

    return int(base_gain + mentor_bonus)


def _get_total_allocated_ap(character: ObjectDB, exclude_pk: int | None = None) -> int:
    """Get total AP currently allocated across all training for a character.

    Args:
        character: The character whose allocations to sum.
        exclude_pk: Optional allocation PK to exclude from the total (used when
            validating an update).

    Returns:
        Total AP allocated, or 0 if none.
    """
    qs = TrainingAllocation.objects.filter(character=character)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.aggregate(total=Sum("ap_amount"))["total"] or 0


def create_training_allocation(
    character: ObjectDB,
    ap_amount: int,
    *,
    skill: Skill | None = None,
    specialization: Specialization | None = None,
    mentor: Persona | None = None,
) -> TrainingAllocation:
    """Create a new training allocation for a character.

    Args:
        character: The character to create the allocation for.
        ap_amount: Action points to allocate.
        skill: The skill to train (mutually exclusive with specialization).
        specialization: The specialization to train (mutually exclusive with skill).
        mentor: Optional mentor persona for the training.

    Returns:
        The created TrainingAllocation instance.

    Raises:
        ValueError: If ap_amount is <= 0 or total allocations would exceed
            the weekly AP budget.
    """
    if ap_amount <= 0:
        msg = "AP amount must be greater than 0."
        raise ValueError(msg)

    budget = ActionPointConfig.get_weekly_regen()
    current_total = _get_total_allocated_ap(character)
    if current_total + ap_amount > budget:
        msg = (
            f"Total allocated AP ({current_total + ap_amount}) would exceed "
            f"weekly budget ({budget})."
        )
        raise ValueError(msg)

    return TrainingAllocation.objects.create(
        character=character,
        skill=skill,
        specialization=specialization,
        mentor=mentor,
        ap_amount=ap_amount,
    )


def update_training_allocation(
    allocation: TrainingAllocation,
    *,
    ap_amount: int | None = None,
    mentor: Persona | None = _UNSET,  # type: ignore[assignment]
) -> TrainingAllocation:
    """Update an existing training allocation.

    Args:
        allocation: The allocation to update.
        ap_amount: New AP amount (if provided).
        mentor: New mentor persona, or None to remove mentor. Pass the sentinel
            ``_UNSET`` (default) to leave unchanged.

    Returns:
        The updated TrainingAllocation instance.

    Raises:
        ValueError: If ap_amount is <= 0 or total allocations would exceed
            the weekly AP budget.
    """
    if ap_amount is not None:
        if ap_amount <= 0:
            msg = "AP amount must be greater than 0."
            raise ValueError(msg)

        budget = ActionPointConfig.get_weekly_regen()
        current_total = _get_total_allocated_ap(allocation.character, exclude_pk=allocation.pk)
        if current_total + ap_amount > budget:
            msg = (
                f"Total allocated AP ({current_total + ap_amount}) would exceed "
                f"weekly budget ({budget})."
            )
            raise ValueError(msg)
        allocation.ap_amount = ap_amount

    if mentor is not _UNSET:
        allocation.mentor = mentor

    allocation.save()
    return allocation


def remove_training_allocation(allocation: TrainingAllocation) -> None:
    """Delete a training allocation.

    Args:
        allocation: The allocation to remove.
    """
    allocation.delete()


def _development_cost(current_value: int) -> int:
    """Calculate the development point cost to reach the next skill level.

    Cost formula: ``max((current_value - 9) * 100, 1)``.

    Examples: 10->11 costs 100, 11->12 costs 200, 15->16 costs 600.

    Args:
        current_value: The current skill or specialization value.

    Returns:
        Development points required to advance one level (minimum 1).
    """
    return max((current_value - 9) * 100, 1)


def _is_at_xp_boundary(value: int) -> bool:
    """Check whether a skill value is at an XP boundary.

    XP boundaries are values ending in 9 within each decade (19, 29, 39, 49).
    At these boundaries, further training development is blocked until XP is
    spent to break through.

    Args:
        value: The current skill value to check.

    Returns:
        True if the value is at an XP boundary.
    """
    return value % 10 == _XP_BOUNDARY_DIGIT and _XP_BOUNDARY_MIN <= value <= _XP_BOUNDARY_MAX


def _apply_development_to_skill(skill_value: CharacterSkillValue, dev_points: int) -> None:
    """Apply development points to a skill, handling rust payoff, level-ups, and overflow.

    Dev points pay off rust first, then count toward advancement. Mutates the
    ``skill_value`` instance in place and saves it. If the skill is at an XP
    boundary (19, 29, 39, 49), all points are wasted.

    Args:
        skill_value: The CharacterSkillValue to develop.
        dev_points: Development points to apply.
    """
    if _is_at_xp_boundary(skill_value.value):
        return

    # Pay off rust first
    remaining = dev_points
    if skill_value.rust_points > 0:
        if remaining >= skill_value.rust_points:
            remaining -= skill_value.rust_points
            skill_value.rust_points = 0
        else:
            skill_value.rust_points -= remaining
            remaining = 0

    # Apply remaining to development
    remaining += skill_value.development_points

    cost = _development_cost(skill_value.value)
    while remaining >= cost:
        remaining -= cost
        skill_value.value += 1
        if _is_at_xp_boundary(skill_value.value):
            remaining = 0
            break
        cost = _development_cost(skill_value.value)

    skill_value.development_points = remaining
    skill_value.save()


def _apply_development_to_specialization(
    spec_value: CharacterSpecializationValue, dev_points: int
) -> None:
    """Apply development points to a specialization, handling level-ups.

    Specializations have no XP boundaries and can level freely. Mutates the
    ``spec_value`` instance in place and saves it.

    Args:
        spec_value: The CharacterSpecializationValue to develop.
        dev_points: Development points to apply.
    """
    spec_value.development_points += dev_points

    cost = _development_cost(spec_value.value)
    while spec_value.development_points >= cost:
        spec_value.development_points -= cost
        spec_value.value += 1
        cost = _development_cost(spec_value.value)

    spec_value.save()


@transaction.atomic
def process_weekly_training() -> dict[int, set[int]]:
    """Process all training allocations for the weekly tick.

    Iterates every ``TrainingAllocation``, calculates development points,
    applies them to the relevant skill or specialization, consumes AP
    from the character's action point pool, and records a
    ``DevelopmentTransaction`` audit trail entry for each allocation.

    Returns:
        A dict mapping character PKs to sets of trained Skill PKs. For
        specialization training the parent skill PK is included (used by
        the rust system to prevent rust on actively trained skills).
    """
    trained_skills: dict[int, set[int]] = defaultdict(set)

    # Pre-fetch the Teaching skill once for all mentor calculations.
    teaching_skill = _get_teaching_skill()

    active_characters = (
        RosterEntry.objects.active_rosters().exclude_frozen().values("character_sheet")
    )
    allocations = list(
        TrainingAllocation.objects.filter(
            character__in=active_characters,
        ).select_related(
            "character",
            "skill",
            "skill__trait",
            "specialization",
            "specialization__parent_skill",
            "specialization__parent_skill__trait",
            "mentor",
            "mentor__character",
        )
    )

    # Batch-fetch path levels for all involved characters (1 query).
    character_pks = {a.character_id for a in allocations}
    path_levels = _bulk_path_levels(character_pks)

    for allocation in allocations:
        character = allocation.character
        dev_points = calculate_training_development(
            allocation, _teaching_skill=teaching_skill, _path_levels=path_levels
        )

        if allocation.skill:
            trait = allocation.skill.trait
            skill_value, _created = CharacterSkillValue.objects.get_or_create(
                character=character,
                skill=allocation.skill,
                defaults={"value": 10, "development_points": 0, "rust_points": 0},
            )
            _apply_development_to_skill(skill_value, dev_points)
            trained_skills[character.pk].add(allocation.skill.pk)
        elif allocation.specialization:
            trait = allocation.specialization.parent_skill.trait
            spec_value, _created = CharacterSpecializationValue.objects.get_or_create(
                character=character,
                specialization=allocation.specialization,
                defaults={"value": 10, "development_points": 0},
            )
            _apply_development_to_specialization(spec_value, dev_points)
            trained_skills[character.pk].add(allocation.specialization.parent_skill_id)
        else:
            continue  # pragma: no cover — XOR constraint prevents this

        # Record audit trail. DevelopmentTransaction uses CharacterSheet FK.
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        sheet, _ = CharacterSheet.objects.get_or_create(character=character)
        DevelopmentTransaction.objects.create(
            character_sheet=sheet,
            trait=trait,
            source=DevelopmentSource.TRAINING,
            amount=dev_points,
            reason=ProgressionReason.SYSTEM_AWARD,
            description=f"Weekly training: {allocation}",
        )

        # Consume AP. Training still processes if pool is missing or has
        # insufficient AP — allocations represent reserved budget, and the
        # weekly AP regen is assumed to have run before training processing.
        try:
            pool = ActionPointPool.objects.get(character=character)
            if not pool.spend(allocation.ap_amount):
                logger.warning(
                    "Insufficient AP for %s: wanted %d, pool has %d",
                    character.db_key,
                    allocation.ap_amount,
                    pool.current,
                )
        except ActionPointPool.DoesNotExist:
            logger.warning(
                "No AP pool for %s during training processing",
                character.db_key,
            )

    return dict(trained_skills)


def run_weekly_skill_cron() -> None:
    """Run the full weekly skill development cycle.

    1. Process all training allocations (award dev points, consume AP).
    2. Apply rust to all untrained skills.
    """
    trained_skills = process_weekly_training()
    apply_weekly_rust(trained_skills)


def apply_weekly_rust(trained_skills: dict[int, set[int]]) -> None:
    """Apply weekly rust to all untrained skills.

    Skills that were actively trained or used this week (present in
    ``trained_skills``) are exempt. All other skills accumulate rust
    equal to ``character_level + 5``, capped at the current level's
    development cost.

    Args:
        trained_skills: Dict from ``process_weekly_training()`` mapping
            character PKs to sets of Skill PKs that were active this week.
    """
    active_characters = (
        RosterEntry.objects.active_rosters().exclude_frozen().values("character_sheet")
    )
    all_skill_values = list(
        CharacterSkillValue.objects.filter(
            character__in=active_characters,
        ).select_related("character")
    )

    # Batch-fetch path levels for all characters with skill values (1 query).
    character_pks = {sv.character_id for sv in all_skill_values}
    path_levels = _bulk_path_levels(character_pks)

    for sv in all_skill_values:
        active_skills = trained_skills.get(sv.character_id, set())
        if sv.skill_id in active_skills:
            continue

        char_level = path_levels.get(sv.character_id, 1)
        rust_amount = char_level + 5
        max_rust = _development_cost(sv.value)
        sv.rust_points = min(sv.rust_points + rust_amount, max_rust)
        sv.save()
