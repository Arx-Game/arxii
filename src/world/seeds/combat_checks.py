"""Combat-skill catalog + Melee Attack check composition (#1706).

Stands up the ``Melee Combat`` parent skill (Trait-backed,
``TraitCategory.COMBAT``) with three weapon-class specializations
(Small / Medium / Heavy Weapons — local to this seed, see
``_WEAPON_SPECIALIZATIONS`` below) and a
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

The other strike skills (#4858), Ranged, Thrown and Unarmed Combat, are seeded the same
way, and the Strike's attack check types (Melee, Ranged, Thrown and Unarmed Attack) are
sampled composed like production's.
"""

from __future__ import annotations

from decimal import Decimal

from world.combat.constants import (
    MELEE_STRIKE_CHECK_TYPE_NAME,
    RANGED_STRIKE_CHECK_TYPE_NAME,
    THROWN_STRIKE_CHECK_TYPE_NAME,
    UNARMED_STRIKE_CHECK_TYPE_NAME,
)

# (specialization name) — weapon-class specs under Melee Combat.
_WEAPON_SPECIALIZATIONS: list[str] = ["Small Weapons", "Medium Weapons", "Heavy Weapons"]

_MELEE_COMBAT_CHECK_TYPE_NAME = "Melee Combat"
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


def ensure_melee_combat_check_type(skill, specs) -> object | None:
    """Look up (or sample) the Melee Combat CheckType: skill + default stat (strength).

    ``checks.checktype``/``checktypetrait`` are content-repo-owned (#2698) —
    returns ``None`` (logged by ``authored_or_sample``) when the category or
    the check type itself isn't authored. The skill's trait leg is skipped
    (not fatal) when ``skill`` is ``None`` — the CheckType may still be
    authored content the lore repo composes with its own trait rows.

    The stat is situational (#2757): the calling system passes ``stat_override``
    based on the equipped weapon. The default stat (strength) is used when no
    override is given (GM ad-hoc, legacy callers).
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
        {"description": "A melee combat roll: skill + situational stat (default strength)."},
        name=_MELEE_COMBAT_CHECK_TYPE_NAME,
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
    # Ensure agility exists as a stat_override target for Melee Combat (#2757):
    # the combat system passes stat_override="agility" for light-weapon offense
    # and defense. The Trait row must exist so handler.get_trait_value works.
    authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL, "is_public": True},
        name="agility",
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


# The other strike skills (#4858): (name, tooltip), each a COMBAT skill like Melee Combat.
_OTHER_STRIKE_SKILLS: tuple[tuple[str, str], ...] = (
    ("Ranged Combat", "Shooting bows, crossbows and slings."),
    ("Thrown Combat", "Throwing knives, axes and javelins."),
    ("Unarmed Combat", "Fighting with fists, wraps or natural weapons."),
)

# The Strike's attack check types (#4858), composed the way production's are: (check
# type, its stats, the strike skill it weights or None). Production's Ranged Attack is
# agility + perception with no skill, and is sampled the same way.
_STRIKE_CHECKS: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    (MELEE_STRIKE_CHECK_TYPE_NAME, ("strength",), _MELEE_SKILL_NAME),
    (RANGED_STRIKE_CHECK_TYPE_NAME, ("agility", "perception"), None),
    (THROWN_STRIKE_CHECK_TYPE_NAME, ("strength",), "Thrown Combat"),
    (UNARMED_STRIKE_CHECK_TYPE_NAME, ("strength",), "Unarmed Combat"),
)


def ensure_strike_skill(name: str, tooltip: str) -> object | None:
    """Look up (or sample) one strike skill and its backing SKILL Trait."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait = authored_or_sample(
        Trait,
        {"trait_type": TraitType.SKILL, "category": TraitCategory.COMBAT, "is_public": True},
        name=name,
    )
    if trait is None:
        return None
    return authored_or_sample(
        Skill, {"tooltip": tooltip, "display_order": 0, "is_active": True}, trait=trait
    )


def ensure_strike_check_type(
    name: str, stat_names: tuple[str, ...], skill_name: str | None
) -> object | None:
    """Look up (or sample) one Strike attack check type: its stats + its strike skill.

    Content rows (``authored_or_sample``): a missing one is skipped when sampling is off.
    """
    from world.checks.models import CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    category = _ensure_combat_category()
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType,
        {"description": f"A Strike's {name.lower()} roll."},
        name=name,
        category=category,
    )
    if check_type is None:
        return None
    weight = Decimal("1.00")
    legs = [
        authored_or_sample(
            Trait,
            {"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL, "is_public": True},
            name=stat_name,
        )
        for stat_name in stat_names
    ]
    if skill_name is not None:
        legs.append(Trait.objects.filter(name=skill_name, trait_type=TraitType.SKILL).first())
    for leg in legs:
        if leg is not None:
            authored_or_sample(CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=leg)
    return check_type


def seed_combat_check_content() -> None:
    """Cluster entry: the strike skills, Melee Combat, and the Strike's attack checks."""
    skill = ensure_melee_combat_skill()
    specs = ensure_weapon_specializations(skill)
    ensure_melee_combat_check_type(skill, specs)
    for name, tooltip in _OTHER_STRIKE_SKILLS:
        ensure_strike_skill(name, tooltip)
    for name, stat_names, skill_name in _STRIKE_CHECKS:
        ensure_strike_check_type(name, stat_names, skill_name)
