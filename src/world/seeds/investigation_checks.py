"""Seed the investigation Search + Identification checks — both ride Investigation (#1705, #1107).

The search action (``actions/definitions/investigation.py``) rolls a ``CheckType`` named
``"Search"`` (``clues.constants.SEARCH_CHECK_TYPE_NAME``) that was **never seeded** — so a search
rolled with no
authored composition and the action degraded to a PLACEHOLDER. Seed the **Investigation** skill
(+ its backing SKILL trait) and the **Search** ``CheckType`` as **perception (stat) + Investigation
(skill)**, authoritatively and idempotently. The specialization layer is optional/future. Mirrors
``world/seeds/social_checks.py``; this is the mystery/investigation core loop's roll.

Also seeds the **Identification** ``CheckType`` (#1107 slice 5, Apostate's 2026-07-03 ruling) —
**intellect (stat) + Investigation (skill)**, the PC-to-PC "recognize who's under the mask"
check. Deliberately a *different* stat pairing than Search: clocking a face from memory/deduction
(intellect) rather than noticing a physical clue (perception).
"""

from __future__ import annotations

from decimal import Decimal

from world.forms.constants import IDENTIFICATION_CHECK_TYPE_NAME

_INVESTIGATION_SKILL = ("Investigation", "Searching, examining, and piecing clues together.")
_SEARCH_STAT = "perception"
_IDENTIFICATION_STAT = "intellect"
_EXPLORATION_CATEGORY = "Exploration"

_LOCKPICKING_CHECK_TYPE_NAME = "Lockpicking"
_WITS_STAT = "wits"


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


def _ensure_intellect_stat():
    """The intellect STAT trait (matches the canonical stat seed: STAT / category META)."""
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name=_IDENTIFICATION_STAT,
        defaults={
            "trait_type": TraitType.STAT,
            "category": TraitCategory.META,
            "is_public": True,
        },
    )
    return trait


def ensure_identification_check():
    """Seed the **Identification** ``CheckType`` — intellect + Investigation (#1107 slice 5).

    Idempotent, authoritative (wipe-and-rewrite composition, matching the Search seed's
    pattern): a viewer's Identification roll always ends up intellect + Investigation, never
    accreting a stale composition from an earlier design. Shares the Investigation skill/trait
    row with Search — one skill backs both the "find the clue" and "recognize the face" rolls.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415

    skill = ensure_investigation_skill()
    stat_trait = _ensure_intellect_stat()
    category, _ = CheckCategory.objects.get_or_create(name=_EXPLORATION_CATEGORY)
    check_type, _ = CheckType.objects.get_or_create(
        name=IDENTIFICATION_CHECK_TYPE_NAME, category=category, defaults={"is_active": True}
    )
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    # Authoritative: wipe any prior composition, then rewrite intellect + Investigation.
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    CheckTypeTrait.objects.create(check_type=check_type, trait=stat_trait, weight=weight)
    CheckTypeTrait.objects.create(check_type=check_type, trait=skill.trait, weight=weight)
    return check_type


def _ensure_wits_stat():
    """The wits STAT trait (matches the canonical stat seed: STAT / category META)."""
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name=_WITS_STAT,
        defaults={
            "trait_type": TraitType.STAT,
            "category": TraitCategory.META,
            "is_public": True,
        },
    )
    return trait


def ensure_lockpicking_check():
    """Seed the **Lockpicking** ``CheckType`` — wits + Skulduggery (#2176, renamed #1825).

    Idempotent, authoritative (wipe-and-rewrite composition): a lockpicking
    roll always ends up wits + Skulduggery, never accreting a stale composition.
    The skill's canonical seed (rename + ensure) lives in ``security_checks``.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.security_checks import ensure_skulduggery_skill  # noqa: PLC0415

    skill = ensure_skulduggery_skill()
    stat_trait = _ensure_wits_stat()
    category, _ = CheckCategory.objects.get_or_create(name=_EXPLORATION_CATEGORY)
    check_type, _ = CheckType.objects.get_or_create(
        name=_LOCKPICKING_CHECK_TYPE_NAME, category=category, defaults={"is_active": True}
    )
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    CheckTypeTrait.objects.create(check_type=check_type, trait=stat_trait, weight=weight)
    CheckTypeTrait.objects.create(check_type=check_type, trait=skill.trait, weight=weight)
    return check_type


def seed_investigation_check_content() -> None:
    """Cluster entry — seed the Investigation skill + the Search + Identification checks."""
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
    ensure_identification_check()
    ensure_lockpicking_check()
