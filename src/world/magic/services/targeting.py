"""Technique targeting predicates.

Pure functions that derive targeting relationship and consent requirements from
authored Technique data. Used by validity enforcement, target resolution, and
cast routing downstream.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from actions.constants import ActionTargetType
from world.magic.models.techniques import ConditionTargetKind, Technique
from world.magic.services.hostility import is_technique_hostile
from world.scenes.models import Persona


class InvalidCastTarget(ValidationError):
    """Raised when a technique's target list violates cardinality or relationship rules."""


def _check_cardinality(
    technique: Technique,
    initiator_sheet_id: int,
    target_personas: list[Persona],
) -> None:
    """Enforce target_type (cardinality) constraints."""
    target_type = technique.target_type

    if target_type == ActionTargetType.SELF:
        for persona in target_personas:
            if persona.character_sheet_id != initiator_sheet_id:
                msg = "This technique can only target the caster, not other characters."
                raise InvalidCastTarget(msg)

    if target_type == ActionTargetType.SINGLE and len(target_personas) > 1:
        count = len(target_personas)
        msg = f"This technique targets at most one character; {count} were provided."
        raise InvalidCastTarget(msg)


def _check_relationship(
    relationship: ConditionTargetKind,
    initiator_sheet_id: int,
    target_personas: list[Persona],
) -> None:
    """Enforce relationship (SELF/ENEMY/ALLY) constraints."""
    if relationship == ConditionTargetKind.SELF:
        for persona in target_personas:
            if persona.character_sheet_id != initiator_sheet_id:
                msg = "This technique's effect can only apply to the caster."
                raise InvalidCastTarget(msg)

    elif relationship == ConditionTargetKind.ENEMY:
        for persona in target_personas:
            if persona.character_sheet_id == initiator_sheet_id:
                msg = "A hostile technique cannot target the caster."
                raise InvalidCastTarget(msg)

    # ALLY: no restriction — self and others are both permitted.


def validate_cast_target(
    *,
    technique: Technique,
    initiator_persona: Persona,
    target_personas: list[Persona],
) -> None:
    """Validate that target_personas are legal for the given technique and initiator.

    Raises InvalidCastTarget with a descriptive message when a rule is violated.
    Returns None on success.

    Rules enforced:
    - target_type == SELF: target_personas must be empty or contain only the initiator.
    - target_type == SINGLE: at most one target.
    - relationship SELF: every target must be the initiator (same character_sheet_id).
    - relationship ENEMY: no target may be the initiator.
    - relationship ALLY: any target is allowed (self included).

    Note: reach/range (combat-positional) is NOT enforced here.
    """
    initiator_sheet_id = initiator_persona.character_sheet_id
    relationship = derive_target_relationship(technique)

    _check_cardinality(technique, initiator_sheet_id, target_personas)
    _check_relationship(relationship, initiator_sheet_id, target_personas)


def derive_target_relationship(technique: Technique) -> ConditionTargetKind:
    """Derive the targeting relationship encoded in a technique's authored data.

    Resolution order:
    1. ENEMY — if the technique is hostile (deals damage or applies ENEMY conditions).
    2. ALLY — if any condition_application has target_kind=ALLY.
    3. SELF — fallback (no hostile traits, no ALLY conditions).
    """
    if is_technique_hostile(technique):
        return ConditionTargetKind.ENEMY
    if technique.condition_applications.filter(target_kind=ConditionTargetKind.ALLY).exists():
        return ConditionTargetKind.ALLY
    return ConditionTargetKind.SELF


def technique_alters_behavior(technique: Technique) -> bool:
    """Return True if any applied condition belongs to a behavior-altering category.

    Behavior-altering conditions (compulsion, charm, fear, etc.) require the
    target's consent before being applied to another PC.
    """
    return technique.condition_applications.filter(
        condition__category__alters_behavior=True
    ).exists()


def cast_requires_consent(technique: Technique) -> bool:
    """Return True if casting this technique on another PC requires their consent.

    Hostile techniques are handled separately by routing; this predicate covers
    the behavior-alteration consent path only.
    """
    return technique_alters_behavior(technique)
