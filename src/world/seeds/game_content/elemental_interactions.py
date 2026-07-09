"""Elemental interaction seed content (#2018).

Seeds canonical damage types, elemental condition templates, the starter
interaction matrix, and setup-condition techniques so two PCs can execute
the emergent synergy play end-to-end.

Idempotent (get_or_create throughout). Called from ``seed_magic_dev()``.
"""

from __future__ import annotations

from world.conditions.models import (
    ConditionCategory,
    ConditionDamageInteraction,
    ConditionTemplate,
    DamageType,
)

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
        damage_types[name], _ = DamageType.objects.get_or_create(name=name)

    # Elemental condition category
    elemental_cat, _ = ConditionCategory.objects.get_or_create(
        name="Elemental",
        defaults={"description": "Elemental conditions affecting the target."},
    )

    # Condition templates
    conditions: dict[str, ConditionTemplate] = {}
    for name in [WET, BURNING, FROZEN, SOAKED]:
        conditions[name], _ = ConditionTemplate.objects.get_or_create(
            name=name,
            defaults={
                "category": elemental_cat,
                "description": f"The target is {name.lower()}.",
            },
        )

    # Interaction matrix
    interactions: list[ConditionDamageInteraction] = []
    for cond_name, dt_name, modifier, removes, applies_name, narration in _INTERACTIONS:
        applies = conditions.get(applies_name) if applies_name else None
        interaction, _ = ConditionDamageInteraction.objects.get_or_create(
            condition=conditions[cond_name],
            damage_type=damage_types[dt_name],
            defaults={
                "damage_modifier_percent": modifier,
                "removes_condition": removes,
                "applies_condition": applies,
                "applied_condition_severity": 1,
                "narration_snippet": narration,
            },
        )
        interactions.append(interaction)

    return {
        "damage_types": damage_types,
        "conditions": conditions,
        "interactions": interactions,
    }
