"""Seed the directed-allure relationship layer — Attracted To / Very Attracted (#1697).

The allure engine (``relationship_gated_contributions``, #1696) reads ``RelationshipCondition``s
whose ``gates_modifiers`` include the ``allure`` ``ModifierTarget`` and folds the perceived's allure
in once per gating condition. This seeds the rows that the ``SET_RELATIONSHIP_CONDITION`` effect
(#1697) sets on a successful flirt/seduction:

- ``allure`` ``ModifierTarget`` — the directed attractiveness value.
- **Attracted To** — the permanent gate (allure ×1), set on the ``conditions`` M2M.
- **Very Attracted** — the temporary gate (the doubling second application), set as an expiring
  ``TemporaryRelationshipCondition``.

Idempotent ``get_or_create``/upserts. The allure *grant* is authored here too (#1697): the
**Attractive** distinction confers base allure per rank via the existing distinction→modifier
materialization; a character without allure modifiers stays at 0 and the engine contributes
nothing. Flirt/Seduce success-effect wiring lives in ``social_actions`` (same cluster run).
"""

from __future__ import annotations

ALLURE_TARGET_NAME = "allure"
ATTRACTED_CONDITION_NAME = "Attracted To"
VERY_ATTRACTED_CONDITION_NAME = "Very Attracted"
_ROLL_MODIFIER_CATEGORY = "roll_modifier"

# PLACEHOLDER base-allure grant per Attractive rank (#1697).
_ATTRACTIVE_ALLURE_PER_RANK = 2

_ATTRACTION_CONDITIONS = [
    (ATTRACTED_CONDITION_NAME, "Drawn to them — their allure colors your regard (permanent)."),
    (VERY_ATTRACTED_CONDITION_NAME, "Smitten — their allure sways you doubly (temporary)."),
]


def ensure_allure_target():
    """The ``allure`` ``ModifierTarget`` (a roll-modifier value the engine reads directionally)."""
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415

    category, _ = ModifierCategory.objects.get_or_create(name=_ROLL_MODIFIER_CATEGORY)
    target, _ = ModifierTarget.objects.get_or_create(
        name=ALLURE_TARGET_NAME,
        category=category,
        defaults={
            "description": "Directed attractiveness — applies when a target is Attracted To you.",
        },
    )
    return target


def ensure_attraction_conditions(allure_target) -> dict[str, object]:
    """Seed Attracted To + Very Attracted, both gating the allure target."""
    from world.relationships.models import RelationshipCondition  # noqa: PLC0415

    conditions: dict[str, object] = {}
    for order, (name, description) in enumerate(_ATTRACTION_CONDITIONS):
        condition, _ = RelationshipCondition.objects.get_or_create(
            name=name, defaults={"description": description, "display_order": order}
        )
        condition.gates_modifiers.add(allure_target)
        conditions[name] = condition
    return conditions


def ensure_attractive_distinction(allure_target) -> None:
    """The Attractive distinction's allure grant (#1697) — closing the authored-content gap.

    A character holding Attractive gets a base allure of
    ``_ATTRACTIVE_ALLURE_PER_RANK × rank`` via the existing distinction→modifier
    materialization (``create_distinction_modifiers``); everyone else stays at
    0 — base allure is simply the sum of allure modifiers. PLACEHOLDER
    magnitude + prose.
    """
    from world.distinctions.models import (  # noqa: PLC0415
        Distinction,
        DistinctionCategory,
        DistinctionEffect,
    )

    category, _ = DistinctionCategory.objects.get_or_create(
        slug="social",
        defaults={"name": "Social", "description": "Social presence and reputation."},
    )
    distinction, _ = Distinction.objects.get_or_create(
        slug="attractive",
        defaults={
            "name": "Attractive",
            "category": category,
            "description": (
                "PLACEHOLDER: Heads turn when you enter the room — a natural magnetism "
                "that colors how the attracted perceive you."
            ),
            "cost_per_rank": 1,
            "max_rank": 3,
        },
    )
    DistinctionEffect.objects.update_or_create(
        distinction=distinction,
        target=allure_target,
        defaults={
            "value_per_rank": _ATTRACTIVE_ALLURE_PER_RANK,
            "description": "Directed allure — applies when a target is Attracted To you.",
        },
    )


def seed_social_relationship_content() -> None:
    """Cluster entry — allure target + attraction conditions + the Attractive grant (#1697)."""
    allure_target = ensure_allure_target()
    ensure_attraction_conditions(allure_target)
    ensure_attractive_distinction(allure_target)
