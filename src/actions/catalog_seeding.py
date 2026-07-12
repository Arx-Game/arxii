"""Shared idempotent seeding machinery for consequence-pool flavor catalogs.

Serves every curated catalog built on the base-pool + flavor-children pattern —
today the magic technique-cast catalog (#1320, ``world/magic/seeds_cast.py``) and
the combat melee-offense catalog (#1995, ``world/combat/seeds_offense.py``). The
shape both share: a base ``ConsequencePool`` holding canonical outcome tiers, plus
single-depth child "flavor" pools (additive ``extra_consequences`` and/or
``weight_overrides`` on the base tiers), each flavor with a matching
``ActionTemplate`` that differs from the base template only by ``consequence_pool``.

The domain modules keep their catalog DATA (the flavor dicts) and public entry
functions; this module carries only the get-or-create machinery. Everything is
idempotent — keyed on natural names, with explicit drift re-wiring via
``update_fields`` (``get_or_create`` won't update FKs on pre-existing rows).

Flavor dict shape (see ``_CATALOG_POOLS`` / ``_COMBAT_CATALOG_POOLS``)::

    {
        "name": str,                       # flavor name, e.g. "Wild Surge"
        "description": str,                # pool description
        "extra_consequences": [            # NEW Consequence rows (additive merge)
            (outcome_tier_name, label, weight), ...
        ],
        "weight_overrides": {              # re-list an existing base consequence
            outcome_tier_name: weight, ...  # at a different weight (override merge)
        },
    }

Naming is derived, not passed: a flavor's pool is ``f"{base_pool.name}: {name}"``
and its template is ``f"{base_template.name}: {name}"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models import ActionTemplate, ConsequencePool
    from world.checks.models import CheckType


def ensure_base_pool(
    *, name: str, description: str, consequences: list[tuple[str, str, int]]
) -> ConsequencePool:
    """Get-or-create a base ConsequencePool holding the canonical outcome tiers.

    ``consequences`` rows are ``(outcome_tier_name, label, weight)``; each becomes a
    ``Consequence`` (get-or-create keyed on tier + label) entered into the pool with
    no override and no exclusion.
    """
    from actions.models import ConsequencePool, ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415
    from world.traits.factories import CheckOutcomeFactory  # noqa: PLC0415

    pool, _ = ConsequencePool.objects.get_or_create(
        name=name,
        defaults={"description": description},
    )
    for outcome_name, label, weight in consequences:
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


def ensure_catalog_content(
    *,
    base_template: ActionTemplate,
    base_consequences: list[tuple[str, str, int]],
    catalog: list[dict],
    category: str,
    description_template: str,
) -> list[ActionTemplate]:
    """Idempotent: seed a curated catalog of consequence-pool flavors as
    single-depth children of ``base_template.consequence_pool``, each with a
    matching ActionTemplate (same check_type/pipeline/target_type as the base
    template — only consequence_pool differs).

    ``description_template`` is formatted with ``flavor_name`` for each flavor's
    template description. Returns the catalog ActionTemplate rows (created or
    pre-existing) in ``catalog`` order.
    """
    base_pool = base_template.consequence_pool
    check_type = base_template.check_type

    base_label_by_tier = {name: label for name, label, _weight in base_consequences}

    templates = []
    for flavor in catalog:
        pool = _ensure_catalog_pool(flavor, base_pool)
        _ensure_catalog_extra_consequences(flavor, pool)
        _apply_catalog_weight_overrides(flavor, pool, base_label_by_tier)
        templates.append(
            _ensure_catalog_template(
                flavor,
                pool,
                base_template,
                check_type,
                category=category,
                description_template=description_template,
            )
        )
    return templates


def _ensure_catalog_pool(flavor: dict, base_pool: ConsequencePool) -> ConsequencePool:
    """Get-or-create the per-flavor child ConsequencePool, reparenting if needed."""
    from actions.models import ConsequencePool  # noqa: PLC0415

    pool_name = f"{base_pool.name}: {flavor['name']}"
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


def _ensure_catalog_template(  # noqa: PLR0913
    flavor: dict,
    pool: ConsequencePool,
    base_template: ActionTemplate,
    check_type: CheckType,
    *,
    category: str,
    description_template: str,
) -> ActionTemplate:
    """Get-or-create the per-flavor ActionTemplate, reconciling divergent fields."""
    from actions.models import ActionTemplate  # noqa: PLC0415

    template_name = f"{base_template.name}: {flavor['name']}"
    template, _ = ActionTemplate.objects.get_or_create(
        name=template_name,
        defaults={
            "check_type": check_type,
            "consequence_pool": pool,
            "category": category,
            "pipeline": base_template.pipeline,
            "target_type": base_template.target_type,
            "description": description_template.format(flavor_name=flavor["name"]),
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
