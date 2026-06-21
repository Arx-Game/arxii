"""Technique targeting predicates.

Pure functions that derive targeting relationship and consent requirements from
authored Technique data. Used by validity enforcement, target resolution, and
cast routing downstream.
"""

from __future__ import annotations

from world.magic.models.techniques import ConditionTargetKind, Technique
from world.magic.services.hostility import is_technique_hostile


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
