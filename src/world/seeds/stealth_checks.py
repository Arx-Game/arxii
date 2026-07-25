"""Stealth check content seed (#1464) — the act-time concealment leg.

Stealth (NEW skill — flagged into the skill audit) is the "was I seen at all"
half of concealment: it reduces who witnesses an act in the first place, while
the social containment tools (Deception/Intimidation/Stewardship) hush the
witnesses afterwards. Seeded now so magic/items can modify it and future
surfaces (burglary, infiltration, the act-time declaration moment) roll it;
the witness-reduction wiring itself is a later surface — the declaration
moment doesn't exist at deed birth yet.

Weights PLACEHOLDER.

``checks.checkcategory``/``checktype``/``checktypetrait``, ``skills.skill``, and
``traits.trait`` are content-repo-owned (#2698) — looked up via
``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT`` is
on. No longer wipes and rewrites the composition on each run (#2698 Part 1 —
that reverted authored/staff-tuned weights on every Big Button press);
``get_or_create``/``authored_or_sample`` converge instead.
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
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait = authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.PHYSICAL,
            "is_public": True,
        },
        name="Stealth",
    )
    if trait is not None:
        authored_or_sample(
            Skill,
            {
                "tooltip": "Moving unseen and unheard — the act-time half of concealment.",
                "display_order": 30,
                "is_active": True,
            },
            trait=trait,
        )
    stat = authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.STAT,
            "category": TraitCategory.PHYSICAL,
            "is_public": True,
        },
        name="agility",
    )
    category = authored_or_sample(
        CheckCategory,
        {
            "description": "Checks of body, movement, and physical craft.",
            "display_order": 20,
        },
        name="Physical",
    )
    if category is None:
        return
    check_type = authored_or_sample(
        CheckType, {"is_active": True}, name="Stealth", category=category
    )
    if check_type is None:
        return
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    if stat is not None:
        authored_or_sample(CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=stat)
    if trait is not None:
        authored_or_sample(CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=trait)
