"""Combat-skill catalog + Melee Attack check composition (#1706).

Stands up the ``Melee Combat`` parent skill (Trait-backed,
``TraitCategory.COMBAT``) with three weapon-class specializations
(Small / Medium / Heavy Weapons — aligned to
``progression.services.scene_integration``'s ``weapon_map`` keys) and a
``Melee Attack`` ``CheckType`` composed as ``strength + Melee Combat
(+ owned weapon specialization)``. Mirrors ``world/seeds/social_checks.py``
(#1689).

Authoritative + idempotent: the ``Melee Attack`` composition is rewritten on
each run (delete + recreate ``CheckTypeTrait`` / ``CheckTypeSpecialization``)
so a re-seed converges, while ``Skill`` / ``Specialization`` / ``Trait`` rows
use ``get_or_create`` (preserving staff edits). Weights are PLACEHOLDER (1.00)
per "build the mechanism, defer the magnitudes".
"""

from __future__ import annotations

from decimal import Decimal

# (specialization name) — weapon-class specs under Melee Combat.
_WEAPON_SPECIALIZATIONS: list[str] = ["Small Weapons", "Medium Weapons", "Heavy Weapons"]

_MELEE_ATTACK_CHECK_TYPE_NAME = "Melee Attack"
_MELEE_SKILL_NAME = "Melee Combat"
_MELEE_SKILL_TOOLTIP = "Fighting with melee weapons — the trained combat skill."


def _ensure_combat_category():
    """Get or create the Combat CheckCategory."""
    from world.checks.models import CheckCategory  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(
        name="Combat",
        defaults={
            "description": "Checks involving physical combat.",
            "display_order": 20,
        },
    )
    return category


def ensure_melee_combat_skill():
    """Seed the Melee Combat Skill + its backing SKILL Trait (idempotent)."""
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name=_MELEE_SKILL_NAME,
        defaults={
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.COMBAT,
            "is_public": True,
        },
    )
    skill, _ = Skill.objects.get_or_create(
        trait=trait,
        defaults={"tooltip": _MELEE_SKILL_TOOLTIP, "display_order": 0, "is_active": True},
    )
    return skill


def ensure_weapon_specializations(skill) -> dict:
    """Seed the three weapon-class Specializations under Melee Combat (idempotent)."""
    from world.skills.models import Specialization  # noqa: PLC0415

    specs: dict[str, object] = {}
    for order, name in enumerate(_WEAPON_SPECIALIZATIONS):
        spec, _ = Specialization.objects.get_or_create(
            parent_skill=skill,
            name=name,
            defaults={"display_order": order, "is_active": True},
        )
        specs[name] = spec
    return specs


def ensure_melee_attack_check_type(skill, specs) -> object:
    """Seed the Melee Attack CheckType: strength + Melee Combat (+ weapon specs).

    Authoritative rewrite (mirrors social_checks.py) — clears the type's prior
    composition then writes the stat + skill legs, so a re-seed converges. The
    weapon-class specializations fold in only when the character owns them
    (#1688 engine).
    """
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )
    from world.traits.factories import StatTraitFactory  # noqa: PLC0415
    from world.traits.models import TraitCategory  # noqa: PLC0415

    check_type, _ = CheckType.objects.get_or_create(
        name=_MELEE_ATTACK_CHECK_TYPE_NAME,
        category=_ensure_combat_category(),
        defaults={"description": "A melee attack roll: strength + Melee Combat."},
    )
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    CheckTypeSpecialization.objects.filter(check_type=check_type).delete()

    CheckTypeTrait.objects.create(
        check_type=check_type,
        trait=StatTraitFactory(name="strength", category=TraitCategory.PHYSICAL),
        weight=Decimal("1.00"),
    )
    CheckTypeTrait.objects.create(
        check_type=check_type,
        trait=skill.trait,
        weight=Decimal("1.00"),
    )
    weight = Decimal("1.00")
    for spec in specs.values():
        CheckTypeSpecialization.objects.create(
            check_type=check_type, specialization=spec, weight=weight
        )
    return check_type


def seed_combat_check_content() -> None:
    """Cluster entry — seed the Melee Combat skill catalog + Melee Attack check (#1706)."""
    skill = ensure_melee_combat_skill()
    specs = ensure_weapon_specializations(skill)
    ensure_melee_attack_check_type(skill, specs)
