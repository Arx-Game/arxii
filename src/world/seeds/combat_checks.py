"""Combat-skill catalog + Melee Attack check composition (#1706).

Stands up the ``Melee Combat`` parent skill (Trait-backed,
``TraitCategory.COMBAT``) with three weapon-class specializations
(Small / Medium / Heavy Weapons — aligned to
``progression.services.scene_integration``'s ``weapon_map`` keys) and a
``Melee Attack`` ``CheckType`` composed as ``strength + Melee Combat
(+ owned weapon specialization)``. Mirrors ``world/seeds/social_checks.py``
(#1689).

``checks.checkcategory``/``checktype``/``checktypetrait``, ``skills.skill``,
and ``traits.trait`` are content-repo-owned (#2698) — looked up via
``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT``
is on. ``skills.specialization``/``checks.checktypespecialization`` stay
outside ``CONTENT_MODELS`` and keep seeding unconditionally via
``get_or_create``, but the composition is no longer wiped and rewritten on
each run (#2698 Part 1) — a re-seed converges via ``get_or_create``, so
authored/staff-edited weights survive. Weights are PLACEHOLDER (1.00) per
"build the mechanism, defer the magnitudes".
"""

from __future__ import annotations

from decimal import Decimal

# (specialization name) — weapon-class specs under Melee Combat.
_WEAPON_SPECIALIZATIONS: list[str] = ["Small Weapons", "Medium Weapons", "Heavy Weapons"]

_MELEE_ATTACK_CHECK_TYPE_NAME = "Melee Attack"
_MELEE_SKILL_NAME = "Melee Combat"
_MELEE_SKILL_TOOLTIP = "Fighting with melee weapons — the trained combat skill."


def _ensure_combat_category():
    """Look up (or, under SEED_SAMPLE_CONTENT, sample) the Combat CheckCategory."""
    from world.checks.models import CheckCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    return authored_or_sample(
        CheckCategory,
        {
            "description": "Checks involving physical combat.",
            "display_order": 20,
        },
        name="Combat",
    )


def ensure_melee_combat_skill():
    """Look up (or sample) the Melee Combat Skill + its backing SKILL Trait."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait = authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.COMBAT,
            "is_public": True,
        },
        name=_MELEE_SKILL_NAME,
    )
    if trait is None:
        return None
    return authored_or_sample(
        Skill,
        {"tooltip": _MELEE_SKILL_TOOLTIP, "display_order": 0, "is_active": True},
        trait=trait,
    )


def ensure_weapon_specializations(skill) -> dict:
    """Seed the three weapon-class Specializations under Melee Combat (idempotent).

    ``skills.specialization`` is not content-repo-owned — stays unconditional.
    Skipped entirely when ``skill`` is absent (its ``parent_skill`` FK is
    required).
    """
    from world.skills.models import Specialization  # noqa: PLC0415

    if skill is None:
        return {}
    specs: dict[str, object] = {}
    for order, name in enumerate(_WEAPON_SPECIALIZATIONS):
        spec, _ = Specialization.objects.get_or_create(
            parent_skill=skill,
            name=name,
            defaults={"display_order": order, "is_active": True},
        )
        specs[name] = spec
    return specs


def ensure_melee_attack_check_type(skill, specs) -> object | None:
    """Look up (or sample) the Melee Attack CheckType: strength + Melee Combat.

    ``checks.checktype``/``checktypetrait`` are content-repo-owned (#2698) —
    returns ``None`` (logged by ``authored_or_sample``) when the category or
    the check type itself isn't authored. The skill's trait leg is skipped
    (not fatal) when ``skill`` is ``None`` — the CheckType may still be
    authored content the lore repo composes with its own trait rows.
    """
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    category = _ensure_combat_category()
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType,
        {"description": "A melee attack roll: strength + Melee Combat."},
        name=_MELEE_ATTACK_CHECK_TYPE_NAME,
        category=category,
    )
    if check_type is None:
        return None

    weight = Decimal("1.00")
    strength = authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL, "is_public": True},
        name="strength",
    )
    if strength is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=strength
        )
    if skill is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=skill.trait
        )
    for spec in specs.values():
        CheckTypeSpecialization.objects.get_or_create(
            check_type=check_type, specialization=spec, defaults={"weight": weight}
        )
    return check_type


_MELEE_DEFENSE_CHECK_TYPE_NAME = "Melee Defense"


def ensure_melee_defense_check_type(skill, specs) -> object | None:
    """Look up (or sample) the Melee Defense CheckType: agility + Melee Combat.

    Mirrors ``ensure_melee_attack_check_type`` but with ``agility`` as the stat
    (evasion) instead of ``strength`` (attack). Reuses the same ``Melee Combat``
    skill + weapon specializations from #1706 — one skill investment covers
    offense and defense. See ``ensure_melee_attack_check_type`` for the
    skip-on-missing-content contract.
    """
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    category = _ensure_combat_category()
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType,
        {"description": "A melee defense roll: agility + Melee Combat."},
        name=_MELEE_DEFENSE_CHECK_TYPE_NAME,
        category=category,
    )
    if check_type is None:
        return None

    weight = Decimal("1.00")
    agility = authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL, "is_public": True},
        name="agility",
    )
    if agility is not None:
        authored_or_sample(CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=agility)
    if skill is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=skill.trait
        )
    for spec in specs.values():
        CheckTypeSpecialization.objects.get_or_create(
            check_type=check_type, specialization=spec, defaults={"weight": weight}
        )
    return check_type


def seed_combat_check_content() -> None:
    """Cluster entry — seed Melee Combat skill catalog + Attack/Defense checks."""
    skill = ensure_melee_combat_skill()
    specs = ensure_weapon_specializations(skill)
    ensure_melee_attack_check_type(skill, specs)
    ensure_melee_defense_check_type(skill, specs)
