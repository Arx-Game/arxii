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
    - It has at least one damage profile with base_damage > 0, OR
    - It applies a condition whose target_kind is ENEMY, OR
    - It strips a condition off a target whose target_kind is ENEMY.

    ``effect_type.base_power`` is deliberately NOT consulted (#3682, ADR-0278).
    It is the magnitude knob for a power-*scaled* effect, not a statement of
    intent: the authored ``Defense`` effect type carries base_power 10, which
    made all 54 Defense techniques classify as hostile — a shield cast at an
    ally routed through ``_route_hostile_cast`` and a self-shield could not name
    its own caster as a target. Scaling is not aggression; the payload rows are
    the only authored statement of who a technique is aimed at.

    A technique with no payload rows at all now reads benign rather than
    inheriting hostility from its effect type. That is the honest answer for
    unauthored data, and it is already reported separately —
    ``technique_is_underspecified`` flags exactly that state on every player and
    staff surface.

    This predicate is derived from authored data only; no model field is read
    or written by this function.

    Reads the technique's ``cached_*`` payload lists rather than issuing its own
    ``.filter().exists()`` queries (#2898). The cast path calls this up to six
    times per cast, so the old shape cost up to eighteen queries for data the
    technique row was already holding.
    """
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
