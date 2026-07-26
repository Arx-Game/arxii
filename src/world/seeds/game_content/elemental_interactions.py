"""Elemental interaction seed content (#2018).

Seeds canonical damage types, elemental condition templates, the starter
interaction matrix, and setup-condition techniques so two PCs can execute
the emergent synergy play end-to-end.

Idempotent (get_or_create throughout). Called from ``seed_magic_dev()``.

``conditions.DamageType``/``ConditionCategory``/``ConditionTemplate``/
``ConditionDamageInteraction`` are all content-repo-owned (#2698) — looked up
rather than invented unless ``SEED_SAMPLE_CONTENT`` is on via
``authored_or_sample``. A missing damage type or condition simply drops that
entry from the returned dicts; the interaction matrix loop below skips any
row whose condition or damage type isn't present.
"""

from __future__ import annotations

from world.conditions.models import (
    ConditionCategory,
    ConditionDamageInteraction,
    ConditionTemplate,
    DamageType,
)
from world.seeds.sample_content import authored_or_sample

# Canonical damage type names.
DAMAGE_TYPE_NAMES = ["Fire", "Cold", "Lightning", "Force", "Acid", "Poison"]

# Elemental condition template names.
WET = "Wet"
BURNING = "Burning"
FROZEN = "Frozen"
SOAKED = "Soaked"

# Interaction matrix: (condition_name, damage_type_name, modifier, removes, applies_name, narration)
_INTERACTIONS: list[tuple[str, str, int, bool, str | None, str]] = [
    (WET, "Lightning", 50, True, None, "the wet flesh crackles with conducted lightning"),
    (WET, "Fire", -30, False, None, ""),  # silent — modifier only, no transition
    (BURNING, "Cold", 0, True, None, "the frost snuffs the flames"),
    (FROZEN, "Force", 50, True, None, "the frozen shell shatters under the blow"),
    (FROZEN, "Fire", 0, True, WET, "the ice melts away"),
    (SOAKED, "Lightning", 50, True, None, "the soaked target conducts the blast"),
]


def seed_elemental_interactions() -> dict[str, object]:
    """Seed canonical damage types, elemental conditions, and interactions.

    Returns:
        Dict with keys 'damage_types', 'conditions', 'interactions' mapping
        to the seeded model instances.
    """
    # Damage types
    damage_types: dict[str, DamageType] = {}
    for name in DAMAGE_TYPE_NAMES:
        damage_type = authored_or_sample(DamageType, {}, name=name)
        if damage_type is not None:
            damage_types[name] = damage_type

    # Elemental condition category
    elemental_cat = authored_or_sample(
        ConditionCategory,
        {"description": "Elemental conditions affecting the target."},
        name="Elemental",
    )

    # Condition templates
    conditions: dict[str, ConditionTemplate] = {}
    for name in [WET, BURNING, FROZEN, SOAKED]:
        condition = authored_or_sample(
            ConditionTemplate,
            {
                "category": elemental_cat,
                "description": f"The target is {name.lower()}.",
            },
            name=name,
        )
        if condition is not None:
            conditions[name] = condition

    # Interaction matrix — skips a row whose condition or damage type isn't present.
    interactions: list[ConditionDamageInteraction] = []
    for cond_name, dt_name, modifier, removes, applies_name, narration in _INTERACTIONS:
        condition = conditions.get(cond_name)
        damage_type = damage_types.get(dt_name)
        if condition is None or damage_type is None:
            continue
        applies = conditions.get(applies_name) if applies_name else None
        interaction = authored_or_sample(
            ConditionDamageInteraction,
            {
                "damage_modifier_percent": modifier,
                "removes_condition": removes,
                "applies_condition": applies,
                "applied_condition_severity": 1,
                "narration_snippet": narration,
            },
            condition=condition,
            damage_type=damage_type,
        )
        if interaction is not None:
            interactions.append(interaction)

    return {
        "damage_types": damage_types,
        "conditions": conditions,
        "interactions": interactions,
    }
