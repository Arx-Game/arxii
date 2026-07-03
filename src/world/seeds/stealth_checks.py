"""Stealth check content seed (#1464) — the act-time concealment leg.

Stealth (NEW skill — flagged into the skill audit) is the "was I seen at all"
half of concealment: it reduces who witnesses an act in the first place, while
the social containment tools (Deception/Intimidation/Stewardship) hush the
witnesses afterwards. Seeded now so magic/items can modify it and future
surfaces (burglary, infiltration, the act-time declaration moment) roll it;
the witness-reduction wiring itself is a later surface — the declaration
moment doesn't exist at deed birth yet.

Mirrors the authoritative pattern of ``social_checks.py``. Weights PLACEHOLDER.
"""

from __future__ import annotations

from decimal import Decimal


def seed_stealth_check_content() -> None:
    """Cluster entry — seed the Stealth skill + the Stealth check composition."""
    from world.checks.models import (  # noqa: PLC0415
        CheckCategory,
        CheckType,
        CheckTypeTrait,
    )
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name="Stealth",
        defaults={
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.PHYSICAL,
            "is_public": True,
        },
    )
    Skill.objects.get_or_create(
        trait=trait,
        defaults={
            "tooltip": "Moving unseen and unheard — the act-time half of concealment.",
            "display_order": 30,
            "is_active": True,
        },
    )
    stat, _ = Trait.objects.get_or_create(
        name="agility",
        defaults={
            "trait_type": TraitType.STAT,
            "category": TraitCategory.PHYSICAL,
            "is_public": True,
        },
    )
    category, _ = CheckCategory.objects.get_or_create(
        name="Physical",
        defaults={
            "description": "Checks of body, movement, and physical craft.",
            "display_order": 20,
        },
    )
    check_type, _ = CheckType.objects.get_or_create(
        name="Stealth", category=category, defaults={"is_active": True}
    )
    # Authoritative: wipe and rewrite the composition.
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    CheckTypeTrait.objects.create(check_type=check_type, trait=stat, weight=weight)
    CheckTypeTrait.objects.create(check_type=check_type, trait=trait, weight=weight)
