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
``per_round_consequence_pool``, etc. on combat models) instead. See ADR-0128.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models import ActionTemplate, ConsequencePool
    from world.checks.models import CheckType

MELEE_OFFENSE_POOL_NAME = "Combat: Melee Offense"
MELEE_ATTACK_TEMPLATE_NAME = "Melee Attack"

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
    from actions.models import ConsequencePool, ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415
    from world.traits.factories import CheckOutcomeFactory  # noqa: PLC0415

    pool, _ = ConsequencePool.objects.get_or_create(
        name=MELEE_OFFENSE_POOL_NAME,
        defaults={"description": "Graded outcomes for a standalone melee attack."},
    )
    for outcome_name, label, weight in _OFFENSE_CONSEQUENCES:
        outcome = CheckOutcomeFactory(name=outcome_name)
        consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=outcome,
            label=label,
            defaults={"weight": weight, "character_loss": False},
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=pool,
            consequence=consequence,
            defaults={"weight_override": None, "is_excluded": False},
        )
    return pool


def get_melee_offense_pool() -> ConsequencePool:
    """Return the shared 'Combat: Melee Offense' base ConsequencePool, seeding the
    'Melee Attack' ActionTemplate (and its pool) if absent."""
    from world.combat.factories import wire_melee_attack_action_template  # noqa: PLC0415

    return wire_melee_attack_action_template().consequence_pool


def _catalog_pool_name(flavor_name: str) -> str:
    return f"{MELEE_OFFENSE_POOL_NAME}: {flavor_name}"


def _catalog_template_name(flavor_name: str) -> str:
    return f"{MELEE_ATTACK_TEMPLATE_NAME}: {flavor_name}"


def ensure_combat_offense_catalog_content() -> list[ActionTemplate]:
    """Idempotent: seed the curated catalog of combat-offense consequence-pool
    flavors as single-depth children of the base 'Combat: Melee Offense' pool,
    each with a matching ActionTemplate (same check_type/pipeline/target_type as
    the base 'Melee Attack' template — only consequence_pool differs).

    Returns the list of catalog ActionTemplate rows (created or pre-existing),
    in `_COMBAT_CATALOG_POOLS` order.
    """
    from world.combat.factories import wire_melee_attack_action_template  # noqa: PLC0415

    base_template = wire_melee_attack_action_template()
    base_pool = base_template.consequence_pool
    check_type = base_template.check_type

    base_label_by_tier = {name: label for name, label, _weight in _OFFENSE_CONSEQUENCES}

    templates = []
    for flavor in _COMBAT_CATALOG_POOLS:
        pool = _ensure_catalog_pool(flavor, base_pool)
        _ensure_catalog_extra_consequences(flavor, pool)
        _apply_catalog_weight_overrides(flavor, pool, base_label_by_tier)
        templates.append(_ensure_catalog_template(flavor, pool, base_template, check_type))
    return templates


def _ensure_catalog_pool(flavor: dict, base_pool: ConsequencePool) -> ConsequencePool:
    """Get-or-create the per-flavor child ConsequencePool, reparenting if needed."""
    from actions.models import ConsequencePool  # noqa: PLC0415

    pool_name = _catalog_pool_name(flavor["name"])
    pool, _ = ConsequencePool.objects.get_or_create(
        name=pool_name,
        defaults={"description": flavor["description"], "parent": base_pool},
    )
    if pool.parent_id != base_pool.pk:
        pool.parent = base_pool
        pool.save(update_fields=["parent"])
    return pool


def _ensure_catalog_extra_consequences(flavor: dict, pool: ConsequencePool) -> None:
    """Get-or-create the flavor's extra consequence entries on ``pool``."""
    from actions.models import ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415
    from world.traits.factories import CheckOutcomeFactory  # noqa: PLC0415

    for outcome_name, label, weight in flavor["extra_consequences"]:
        outcome = CheckOutcomeFactory(name=outcome_name)
        consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=outcome,
            label=label,
            defaults={"weight": weight, "character_loss": False},
        )
        ConsequencePoolEntry.objects.get_or_create(pool=pool, consequence=consequence)


def _apply_catalog_weight_overrides(
    flavor: dict, pool: ConsequencePool, base_label_by_tier: dict[str, str]
) -> None:
    """Apply the flavor's weight overrides onto shared base-tier consequences."""
    from actions.models import ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415

    for outcome_name, override_weight in flavor["weight_overrides"].items():
        consequence = Consequence.objects.get(
            outcome_tier__name=outcome_name, label=base_label_by_tier[outcome_name]
        )
        entry, _ = ConsequencePoolEntry.objects.get_or_create(
            pool=pool,
            consequence=consequence,
            defaults={"weight_override": override_weight},
        )
        if entry.weight_override != override_weight:
            entry.weight_override = override_weight
            entry.save(update_fields=["weight_override"])


def _ensure_catalog_template(
    flavor: dict, pool: ConsequencePool, base_template: ActionTemplate, check_type: CheckType
) -> ActionTemplate:
    """Get-or-create the per-flavor ActionTemplate, reconciling divergent fields."""
    from actions.models import ActionTemplate  # noqa: PLC0415

    template_name = _catalog_template_name(flavor["name"])
    template, _ = ActionTemplate.objects.get_or_create(
        name=template_name,
        defaults={
            "check_type": check_type,
            "consequence_pool": pool,
            "category": "combat",
            "pipeline": base_template.pipeline,
            "target_type": base_template.target_type,
            "description": (
                f"Standalone resolution spec for a melee attack ({flavor['name']} flavor)."
            ),
        },
    )
    changed = []
    if template.check_type_id != check_type.pk:
        template.check_type = check_type
        changed.append("check_type")
    if template.consequence_pool_id != pool.pk:
        template.consequence_pool = pool
        changed.append("consequence_pool")
    if changed:
        template.save(update_fields=changed)
    return template
