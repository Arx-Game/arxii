"""Service functions for the skills training system."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum

from world.action_points.models import ActionPointConfig, ActionPointPool
from world.relationships.helpers import get_relationship_tier
from world.skills.models import (
    CharacterSkillValue,
    CharacterSpecializationValue,
    Skill,
    Specialization,
    TrainingAllocation,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import Guise

_UNSET = object()


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


def _get_spec_value(character: ObjectDB, specialization_id: int) -> int:
    """Look up a character's value for a given specialization.

    Args:
        character: The character to look up.
        specialization_id: The primary key of the specialization to query.

    Returns:
        The raw specialization value, or 0 if the character has no value for it.
    """
    try:
        return CharacterSpecializationValue.objects.get(
            character=character, specialization_id=specialization_id
        ).value
    except CharacterSpecializationValue.DoesNotExist:
        return 0


def _get_teaching_value(mentor_character: ObjectDB) -> int:
    """Look up the mentor's Teaching skill value.

    Finds the Skill whose linked trait is named "Teaching", then returns the
    mentor's value for that skill.

    Args:
        mentor_character: The mentor character to look up.

    Returns:
        The mentor's Teaching skill value, or 0 if the Teaching skill does not
        exist or the mentor has no value for it.
    """
    try:
        teaching_skill = Skill.objects.get(trait__name="Teaching")
    except Skill.DoesNotExist:
        return 0
    return _get_skill_value(mentor_character, teaching_skill)


def calculate_training_development(allocation: TrainingAllocation) -> int:
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

    Returns:
        Development points as an integer (truncated).
    """
    character = allocation.character
    ap_spent = allocation.ap_amount

    path_level = _get_path_level(character)
    base_gain = 5 * ap_spent * path_level

    if not allocation.mentor:
        return int(base_gain)

    mentor_character = allocation.mentor.character
    teaching = _get_teaching_value(mentor_character)

    if allocation.specialization:
        # Specialization training: include parent skill in totals
        spec = allocation.specialization
        parent_skill = spec.parent_skill

        student_parent = _get_skill_value(character, parent_skill)
        student_spec = _get_spec_value(character, spec.pk)
        student_total = student_parent + student_spec

        mentor_parent = _get_skill_value(mentor_character, parent_skill)
        mentor_spec = _get_spec_value(mentor_character, spec.pk)
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
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.aggregate(total=Sum("ap_amount"))["total"] or 0


def create_training_allocation(
    character: ObjectDB,
    ap_amount: int,
    *,
    skill: Skill | None = None,
    specialization: Specialization | None = None,
    mentor: Guise | None = None,
) -> TrainingAllocation:
    """Create a new training allocation for a character.

    Args:
        character: The character to create the allocation for.
        ap_amount: Action points to allocate.
        skill: The skill to train (mutually exclusive with specialization).
        specialization: The specialization to train (mutually exclusive with skill).
        mentor: Optional mentor guise for the training.

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
    mentor: Guise | None = _UNSET,  # type: ignore[assignment]
) -> TrainingAllocation:
    """Update an existing training allocation.

    Args:
        allocation: The allocation to update.
        ap_amount: New AP amount (if provided).
        mentor: New mentor guise, or None to remove mentor. Pass the sentinel
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

    Cost formula: ``(current_value - 9) * 100``.

    Examples: 10->11 costs 100, 11->12 costs 200, 15->16 costs 600.

    Args:
        current_value: The current skill or specialization value.

    Returns:
        Development points required to advance one level.
    """
    return (current_value - 9) * 100


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
    return value in (19, 29, 39, 49)


def _apply_development_to_skill(skill_value: CharacterSkillValue, dev_points: int) -> None:
    """Apply development points to a skill, handling level-ups and overflow.

    Mutates the ``skill_value`` instance in place and saves it. If the skill
    is at an XP boundary (19, 29, 39, 49), all points are wasted.

    Args:
        skill_value: The CharacterSkillValue to develop.
        dev_points: Development points to apply.
    """
    if _is_at_xp_boundary(skill_value.value):
        skill_value.save()
        return

    skill_value.development_points += dev_points

    cost = _development_cost(skill_value.value)
    while skill_value.development_points >= cost:
        skill_value.development_points -= cost
        skill_value.value += 1
        if _is_at_xp_boundary(skill_value.value):
            skill_value.development_points = 0
            break
        cost = _development_cost(skill_value.value)

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
    applies them to the relevant skill or specialization, and consumes AP
    from the character's action point pool.

    Returns:
        A dict mapping character PKs to sets of trained Skill PKs. For
        specialization training the parent skill PK is included (used by
        the rust system to prevent rust on actively trained skills).
    """
    trained_skills: dict[int, set[int]] = defaultdict(set)

    allocations = TrainingAllocation.objects.select_related(
        "character",
        "skill",
        "specialization",
        "specialization__parent_skill",
        "mentor",
    ).all()

    for allocation in allocations:
        character = allocation.character
        dev_points = calculate_training_development(allocation)

        if allocation.skill:
            skill_value, _created = CharacterSkillValue.objects.get_or_create(
                character=character,
                skill=allocation.skill,
                defaults={"value": 10, "development_points": 0, "rust_points": 0},
            )
            _apply_development_to_skill(skill_value, dev_points)
            trained_skills[character.pk].add(allocation.skill.pk)
        elif allocation.specialization:
            spec_value, _created = CharacterSpecializationValue.objects.get_or_create(
                character=character,
                specialization=allocation.specialization,
                defaults={"value": 10, "development_points": 0},
            )
            _apply_development_to_specialization(spec_value, dev_points)
            trained_skills[character.pk].add(allocation.specialization.parent_skill_id)

        # Consume AP
        try:
            pool = ActionPointPool.objects.get(character=character)
            pool.spend(allocation.ap_amount)
        except ActionPointPool.DoesNotExist:
            pass

    return dict(trained_skills)
