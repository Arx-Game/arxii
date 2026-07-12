"""Idempotent seed for the shared standalone technique-cast scaffolding (#1306)."""

from __future__ import annotations

from decimal import Decimal

TECHNIQUE_CAST_TEMPLATE_NAME = "Technique Cast"
TECHNIQUE_CAST_CHECK_TYPE_NAME = "Technique Cast"
TECHNIQUE_CAST_POOL_NAME = "Magic: Technique Cast"

# (outcome_tier_name, label, weight)
_CAST_CONSEQUENCES = [
    ("Failure", "The cast falters.", 1),
    ("Partial Success", "The cast lands, imperfectly.", 1),
    ("Success", "The cast lands cleanly.", 1),
]
# fallback check trait composition (tuning placeholder; staff-tunable)
_FALLBACK_TRAITS = [("willpower", "1.00"), ("occult", "1.00")]

# Curated catalog: children of the base "Magic: Technique Cast" pool (#1320).
# Each flavor's "extra_consequences" adds NEW Consequence rows (exercising the
# additive merge path in ConsequencePool.cached_consequences); "weight_overrides"
# re-lists an EXISTING base-pool consequence at a different weight (the override
# merge path). Structural placeholders — not final game copy.
_CATALOG_POOLS = [
    {
        "name": "Wild Surge",
        "description": (
            "A swingier flavor: cast failures occasionally erupt into a dramatic "
            "backlash; successes land a little more often to compensate."
        ),
        "extra_consequences": [
            ("Failure", "The cast overloads — a dramatic backlash flares.", 1),
        ],
        "weight_overrides": {"Success": 2},
    },
    {
        "name": "Precise Working",
        "description": (
            "A narrower, safer flavor: partial successes and successes are more "
            "common, at the cost of dramatic flair."
        ),
        "extra_consequences": [],
        "weight_overrides": {"Partial Success": 2, "Success": 2},
    },
]


def _ensure_fallback_check_type():
    from world.checks.models import CheckType, CheckTypeAspect, CheckTypeTrait  # noqa: PLC0415
    from world.magic.seeds_checks import (  # noqa: PLC0415
        _ensure_arcana_aspect,
        ensure_magic_check_category,
        ensure_magic_skills,
    )
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    ensure_magic_skills()  # ensures occult Trait/Skill exist
    category = ensure_magic_check_category()
    arcana = _ensure_arcana_aspect()
    check_type, _ = CheckType.objects.get_or_create(
        name=TECHNIQUE_CAST_CHECK_TYPE_NAME,
        category=category,
        defaults={
            "description": "Fallback check for casting a technique standalone.",
            "is_active": True,
        },
    )
    for trait_name, weight in _FALLBACK_TRAITS:
        trait = Trait.objects.filter(name=trait_name).first()
        if trait is None:
            trait, _ = Trait.objects.get_or_create(
                name=trait_name, defaults={"trait_type": TraitType.STAT, "is_public": True}
            )
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type, trait=trait, defaults={"weight": Decimal(weight)}
        )
    CheckTypeAspect.objects.get_or_create(
        check_type=check_type, aspect=arcana, defaults={"weight": Decimal("1.00")}
    )
    return check_type


def _ensure_cast_pool():
    from actions.catalog_seeding import ensure_base_pool  # noqa: PLC0415

    return ensure_base_pool(
        name=TECHNIQUE_CAST_POOL_NAME,
        description="Graded outcomes for a standalone technique cast.",
        consequences=_CAST_CONSEQUENCES,
    )


def ensure_technique_cast_content():
    """Idempotent: seed the fallback CheckType, graded ConsequencePool, and ActionTemplate.

    Returns the ActionTemplate row (created or pre-existing). FK re-wiring ensures the
    template is correctly linked even when called on a pre-existing row.
    """
    from actions.constants import ActionTargetType, Pipeline  # noqa: PLC0415
    from actions.models import ActionTemplate  # noqa: PLC0415

    check_type = _ensure_fallback_check_type()
    pool = _ensure_cast_pool()
    template, _ = ActionTemplate.objects.get_or_create(
        name=TECHNIQUE_CAST_TEMPLATE_NAME,
        defaults={
            "check_type": check_type,
            "consequence_pool": pool,
            "category": "magic",
            "pipeline": Pipeline.SINGLE,
            "target_type": ActionTargetType.SELF,
            "description": "Standalone resolution spec for casting a technique.",
        },
    )
    # get_or_create won't update FKs on a pre-existing row — ensure wiring.
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


def get_standalone_cast_template():
    """Return the shared Technique Cast ActionTemplate, seeding it if absent."""
    from actions.models import ActionTemplate  # noqa: PLC0415

    template = ActionTemplate.objects.filter(name=TECHNIQUE_CAST_TEMPLATE_NAME).first()
    return template or ensure_technique_cast_content()


def get_standalone_cast_pool():
    """Return the shared 'Magic: Technique Cast' base ConsequencePool, seeding it if absent."""
    return get_standalone_cast_template().consequence_pool


def ensure_technique_catalog_content():
    """Idempotent: seed the curated catalog of technique-cast consequence-pool
    flavors as single-depth children of the base pool, each with a matching
    ActionTemplate (same check_type/pipeline/target_type as the base template;
    only consequence_pool differs). Machinery lives in
    ``actions.catalog_seeding`` (shared with the combat offense catalog, #1995).

    Returns the list of catalog ActionTemplate rows (created or pre-existing),
    in `_CATALOG_POOLS` order.
    """
    from actions.catalog_seeding import ensure_catalog_content  # noqa: PLC0415

    return ensure_catalog_content(
        base_template=ensure_technique_cast_content(),
        base_consequences=_CAST_CONSEQUENCES,
        catalog=_CATALOG_POOLS,
        category="magic",
        description_template=(
            "Standalone resolution spec for casting a technique ({flavor_name} flavor)."
        ),
    )
