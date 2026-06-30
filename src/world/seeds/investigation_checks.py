"""Seed the investigation Search check — perception + Investigation (#1705).

The search action (``actions/definitions/investigation.py``) rolls a ``CheckType`` named
``"Search"`` (``clues.constants.SEARCH_CHECK_TYPE_NAME``) that was **never seeded** — so a search
rolled with no
authored composition and the action degraded to a PLACEHOLDER. Seed the **Investigation** skill
(+ its backing SKILL trait) and the **Search** ``CheckType`` as **perception (stat) + Investigation
(skill)**, authoritatively and idempotently. The specialization layer is optional/future. Mirrors
``world/seeds/social_checks.py``; this is the mystery/investigation core loop's roll.
"""

from __future__ import annotations

from decimal import Decimal

_INVESTIGATION_SKILL = ("Investigation", "Searching, examining, and piecing clues together.")
_SEARCH_STAT = "perception"
_EXPLORATION_CATEGORY = "Exploration"


def ensure_investigation_skill():
    """Seed the Investigation ``Skill`` (+ its backing SKILL ``Trait``)."""
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    name, tooltip = _INVESTIGATION_SKILL
    trait, _ = Trait.objects.get_or_create(
        name=name,
        defaults={
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.GENERAL,
            "is_public": True,
        },
    )
    skill, _ = Skill.objects.get_or_create(
        trait=trait,
        defaults={"tooltip": tooltip, "display_order": 0, "is_active": True},
    )
    return skill


def _ensure_perception_stat():
    """The perception STAT trait (matches the canonical stat seed: STAT / category META)."""
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name=_SEARCH_STAT,
        defaults={
            "trait_type": TraitType.STAT,
            "category": TraitCategory.META,
            "is_public": True,
        },
    )
    return trait


def seed_investigation_check_content() -> None:
    """Cluster entry — seed the Investigation skill + the Search check (perception + skill)."""
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.clues.constants import SEARCH_CHECK_TYPE_NAME  # noqa: PLC0415

    skill = ensure_investigation_skill()
    stat_trait = _ensure_perception_stat()
    category, _ = CheckCategory.objects.get_or_create(name=_EXPLORATION_CATEGORY)
    check_type, _ = CheckType.objects.get_or_create(
        name=SEARCH_CHECK_TYPE_NAME, category=category, defaults={"is_active": True}
    )
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    # Authoritative: wipe any prior composition, then rewrite perception + Investigation.
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    CheckTypeTrait.objects.create(check_type=check_type, trait=stat_trait, weight=weight)
    CheckTypeTrait.objects.create(check_type=check_type, trait=skill.trait, weight=weight)
