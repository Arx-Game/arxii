"""Service functions for the skills training system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.relationships.helpers import get_relationship_tier
from world.skills.models import (
    CharacterSkillValue,
    CharacterSpecializationValue,
    Skill,
    TrainingAllocation,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


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
