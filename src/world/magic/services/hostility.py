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
    """
    if technique.effect_type_id is not None and technique.effect_type.base_power is not None:
        return True
    if technique.damage_profiles.filter(base_damage__gt=0).exists():
        return True
    return technique.condition_applications.filter(target_kind=ConditionTargetKind.ENEMY).exists()
