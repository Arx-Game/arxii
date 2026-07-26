"""Seed the investigation Search + Identification checks — both ride Investigation (#1705, #1107).

The search action (``actions/definitions/investigation.py``) rolls a ``CheckType`` named
``"Search"`` (``clues.constants.SEARCH_CHECK_TYPE_NAME``) that was **never seeded** — so a search
rolled with no
authored composition and the action degraded to a PLACEHOLDER. Seed the **Investigation** skill
(+ its backing SKILL trait) and the **Search** ``CheckType`` as **perception (stat) + Investigation
(skill)**, idempotently. The specialization layer is optional/future. Mirrors
``world/seeds/social_checks.py``; this is the mystery/investigation core loop's roll.

Also seeds the **Identification** ``CheckType`` (#1107 slice 5, Apostate's 2026-07-03 ruling) —
**intellect (stat) + Investigation (skill)**, the PC-to-PC "recognize who's under the mask"
check. Deliberately a *different* stat pairing than Search: clocking a face from memory/deduction
(intellect) rather than noticing a physical clue (perception).

``checks.checkcategory``/``checktype``/``checktypetrait``, ``skills.skill``, and
``traits.trait`` are content-repo-owned (#2698) — looked up via
``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT`` is
on. No longer wipes and rewrites a composition on each run (#2698 Part 1 — that
reverted authored/staff-tuned weights on every Big Button press);
``get_or_create``/``authored_or_sample`` converge instead.
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
    """Look up (or sample) the Investigation ``Skill`` + its backing SKILL ``Trait``.

    ``skills.Skill``/``traits.Trait`` are content-repo-owned (#2698). Returns
    ``None`` when either isn't authored.
    """
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    name, tooltip = _INVESTIGATION_SKILL
    trait = authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.GENERAL,
            "is_public": True,
        },
        name=name,
    )
    if trait is None:
        return None
    return authored_or_sample(
        Skill,
        {"tooltip": tooltip, "display_order": 0, "is_active": True},
        trait=trait,
    )


def _ensure_perception_stat():
    """Look up (or sample) the perception STAT trait — content-repo-owned (#2698)."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    return authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.STAT,
            "category": TraitCategory.META,
            "is_public": True,
        },
        name=_SEARCH_STAT,
    )


def _ensure_intellect_stat():
    """Look up (or sample) the intellect STAT trait — content-repo-owned (#2698)."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    return authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.STAT,
            "category": TraitCategory.META,
            "is_public": True,
        },
        name=_IDENTIFICATION_STAT,
    )


def _ensure_exploration_category():
    """Look up (or sample) the Exploration CheckCategory — content-repo-owned (#2698)."""
    from world.checks.models import CheckCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    return authored_or_sample(CheckCategory, {}, name=_EXPLORATION_CATEGORY)


def ensure_identification_check():
    """Look up (or sample) the **Identification** ``CheckType`` (#1107 slice 5).

    ``checks.CheckCategory``/``CheckType``/``CheckTypeTrait`` are content-repo-owned
    (#2698) — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    No longer wipes and rewrites the composition on each run (#2698 Part 1); shares
    the Investigation skill/trait row with Search.
    """
    from world.checks.models import CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    skill = ensure_investigation_skill()
    stat_trait = _ensure_intellect_stat()
    category = _ensure_exploration_category()
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType,
        {"is_active": True},
        name=IDENTIFICATION_CHECK_TYPE_NAME,
        category=category,
    )
    if check_type is None:
        return None
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    if stat_trait is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=stat_trait
        )
    if skill is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=skill.trait
        )
    return check_type


def _ensure_wits_stat():
    """Look up (or sample) the wits STAT trait — content-repo-owned (#2698)."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    return authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.STAT,
            "category": TraitCategory.META,
            "is_public": True,
        },
        name=_WITS_STAT,
    )


def ensure_lockpicking_check():
    """Look up (or sample) the **Lockpicking** ``CheckType`` (#2176, renamed #1825).

    ``checks.CheckCategory``/``CheckType``/``CheckTypeTrait`` are content-repo-owned
    (#2698) — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    No longer wipes and rewrites the composition on each run (#2698 Part 1). The
    skill's canonical seed (rename + ensure) lives in ``security_checks``.
    """
    from world.checks.models import CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.seeds.security_checks import ensure_skulduggery_skill  # noqa: PLC0415

    skill = ensure_skulduggery_skill()
    stat_trait = _ensure_wits_stat()
    category = _ensure_exploration_category()
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType,
        {"is_active": True},
        name=_LOCKPICKING_CHECK_TYPE_NAME,
        category=category,
    )
    if check_type is None:
        return None
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    if stat_trait is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=stat_trait
        )
    if skill is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=skill.trait
        )
    return check_type


def seed_investigation_check_content() -> None:
    """Cluster entry — seed the Investigation skill + the Search + Identification checks."""
    from world.checks.models import CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.clues.constants import SEARCH_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    skill = ensure_investigation_skill()
    stat_trait = _ensure_perception_stat()
    category = _ensure_exploration_category()
    if category is not None:
        check_type = authored_or_sample(
            CheckType,
            {"is_active": True},
            name=SEARCH_CHECK_TYPE_NAME,
            category=category,
        )
        if check_type is not None:
            weight = Decimal("1.0")  # PLACEHOLDER magnitudes
            if stat_trait is not None:
                authored_or_sample(
                    CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=stat_trait
                )
            if skill is not None:
                authored_or_sample(
                    CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=skill.trait
                )
    ensure_identification_check()
    ensure_lockpicking_check()
