"""Derived hostility classifier for Technique instances.

A technique is "hostile" iff it deals damage or applies enemy-targeting
conditions. This is purely derived — no model field is added.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.models.techniques import ConditionTargetKind

if TYPE_CHECKING:
    from world.magic.models.techniques import Technique


def is_technique_hostile(technique: Technique) -> bool:
    """Return True if the technique deals damage or applies enemy-targeting conditions.

    Hostile means the technique targets an adversary in some mechanical sense:
    - Its effect_type has a non-null base_power (power-scaled offensive effect), OR
    - It has at least one damage profile with base_damage > 0, OR
    - It applies a condition whose target_kind is ENEMY.

    This predicate is derived from authored data only; no model field is read
    or written by this function.

    Reads the technique's ``cached_*`` payload lists rather than issuing its own
    ``.filter().exists()`` queries (#2898). The cast path calls this up to six
    times per cast, so the old shape cost up to eighteen queries for data the
    technique row was already holding.
    """
    if technique.effect_type.base_power is not None:
        return True
    if any(profile.base_damage > 0 for profile in technique.cached_damage_profiles):
        return True
    if any(
        row.target_kind == ConditionTargetKind.ENEMY
        for row in technique.cached_condition_applications
    ):
        return True
    # Stripping a condition off an enemy (e.g. dispelling an enemy's buff) targets an
    # adversary in a mechanical sense, so a removal row targeting ENEMY is hostile (#1585).
    return any(
        row.target_kind == ConditionTargetKind.ENEMY for row in technique.cached_removed_conditions
    )
