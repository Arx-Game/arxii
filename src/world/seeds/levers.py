"""Author the five lever categories and their targets on a dev or E2E database (#4394).

``ModifierCategory``/``ModifierTarget`` are content-repo owned (#2698): on production staff
author these rows (the admin, or the content repo's export), so this looks them up and only
creates them when ``SEED_SAMPLE_CONTENT`` is on, the same shape as ``ensure_menace_target``.
A missing row makes its lever read as 0, nothing else.
"""

from __future__ import annotations

from world.mechanics.constants import LEVER_TARGETS

_CATEGORY_DESCRIPTIONS = {
    "income": "Percent change to what a character personally collects (allowance, assets).",
    "reputation_gain": "Percent change to reputation gained with societies and organizations.",
    "relationship_gain": "Percent change to affection a character's regard gains.",
    "comfort": "Flat shift, in comfort levels, to the comfort a residence yields the character.",
    "fatigue_cost": "Percent change to the fatigue an action charges the character.",
}


def ensure_lever_targets() -> None:
    """Look up (or, with sample content on, create) the five lever categories and targets."""
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    for category_name, target_name in LEVER_TARGETS:
        category = authored_or_sample(
            ModifierCategory,
            {"description": _CATEGORY_DESCRIPTIONS[category_name]},
            name=category_name,
        )
        if category is None:
            continue
        authored_or_sample(
            ModifierTarget,
            {"description": _CATEGORY_DESCRIPTIONS[category_name]},
            category=category,
            name=target_name,
        )
