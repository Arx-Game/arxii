"""Idempotent seed for the combat offense consequence-pool flavor catalog (#1995).

Mirrors ``world/magic/seeds_cast.py``'s shared cast scaffolding + catalog pattern,
applied to the combat "Melee Attack" standalone-cast ActionTemplate (seeded by
``world.combat.factories.wire_melee_attack_action_template``). A PHYSICAL technique
resolves onto this base pool (or one of its curated flavor children) via
``world.magic.services.technique_builder.resolve_cast_action_template`` exactly the
way a non-PHYSICAL technique resolves onto the magic "Technique Cast" catalog.

This catalog applies ONLY to standalone technique casts. Combat ROUNDS deliberately
do not consume ``ActionTemplate.consequence_pool`` at all — round resolution reads
its own combat-specific pools (``on_hit_consequence_pool``, ``resolution_consequence_pool``,
``per_round_consequence_pool``, etc. on combat models) instead. See ADR-0130.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models import ActionTemplate, ConsequencePool

MELEE_OFFENSE_POOL_NAME = "Combat: Melee Offense"

# (outcome_tier_name, label, weight) — same canonical tier names as
# world.magic.seeds_cast._CAST_CONSEQUENCES.
_OFFENSE_CONSEQUENCES = [
    ("Failure", "The strike goes wide.", 1),
    ("Partial Success", "The strike lands, but glances.", 1),
    ("Success", "The strike lands true.", 1),
]

# Curated catalog: children of the base "Combat: Melee Offense" pool. Mirrors
# world.magic.seeds_cast._CATALOG_POOLS's additive-merge / weight-override shape.
# Structural placeholders — not final game copy.
_COMBAT_CATALOG_POOLS = [
    {
        "name": "Brutal",
        "description": (
            "A swingier flavor: failures leave you dangerously overcommitted; "
            "clean hits occasionally land with brutal follow-through."
        ),
        "extra_consequences": [
            ("Failure", "Overcommitted — you are wide open.", 2),
            ("Success", "The strike lands with brutal follow-through.", 2),
        ],
        "weight_overrides": {"Failure": 2, "Success": 2},
    },
    {
        "name": "Precise",
        "description": (
            "A narrower, controlled flavor: partial successes and successes are "
            "more common, at the cost of dramatic flair."
        ),
        "extra_consequences": [],
        "weight_overrides": {"Partial Success": 2, "Success": 2},
    },
]


def ensure_melee_offense_pool() -> ConsequencePool:
    """Idempotent: seed the base 'Combat: Melee Offense' ConsequencePool with the
    3 canonical tiers (weight 1 each — same tier names as the magic cast pool).

    Returns the ConsequencePool row (created or pre-existing)."""
    from actions.catalog_seeding import ensure_base_pool  # noqa: PLC0415

    return ensure_base_pool(
        name=MELEE_OFFENSE_POOL_NAME,
        description="Graded outcomes for a standalone melee attack.",
        consequences=_OFFENSE_CONSEQUENCES,
    )


def get_melee_offense_pool() -> ConsequencePool:
    """Return the shared 'Combat: Melee Offense' base ConsequencePool, seeding the
    'Melee Attack' ActionTemplate (and its pool) if absent."""
    from world.combat.factories import wire_melee_attack_action_template  # noqa: PLC0415

    return wire_melee_attack_action_template().consequence_pool


def ensure_combat_offense_catalog_content() -> list[ActionTemplate]:
    """Idempotent: seed the curated catalog of combat-offense consequence-pool
    flavors as single-depth children of the base 'Combat: Melee Offense' pool,
    each with a matching ActionTemplate (same check_type/pipeline/target_type as
    the base 'Melee Attack' template — only consequence_pool differs). Machinery
    lives in ``actions.catalog_seeding`` (shared with the magic catalog, #1320).

    Returns the list of catalog ActionTemplate rows (created or pre-existing),
    in `_COMBAT_CATALOG_POOLS` order.
    """
    from actions.catalog_seeding import ensure_catalog_content  # noqa: PLC0415
    from world.combat.factories import wire_melee_attack_action_template  # noqa: PLC0415

    return ensure_catalog_content(
        base_template=wire_melee_attack_action_template(),
        base_consequences=_OFFENSE_CONSEQUENCES,
        catalog=_COMBAT_CATALOG_POOLS,
        category="combat",
        description_template=(
            "Standalone resolution spec for a melee attack ({flavor_name} flavor)."
        ),
    )
