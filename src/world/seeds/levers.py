"""Author the lever categories and their targets on a dev or E2E database (#4394, #4396).

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
    "disguise_sight": (
        "Sight through a mask: a positive total on a kind's target sees who is behind a "
        "disguise of that kind without the identification check."
    ),
}


def ensure_aspect_targets() -> None:
    """One aspect-category target per ``Aspect`` row (#4827), through ``ensure_aspect_target``.

    ``ModifierTarget`` rows are content (#2698), so this invents them only when sample
    content is on, the same rule as ``ensure_lever_targets``. On production the Aspect
    admin's save makes an Aspect's target (``AspectAdmin.save_model``).
    """
    from world.classes.models import Aspect  # noqa: PLC0415
    from world.mechanics.services import ensure_aspect_target  # noqa: PLC0415
    from world.seeds.sample_content import sample_content_enabled  # noqa: PLC0415

    if not sample_content_enabled():
        return
    for aspect in Aspect.objects.all():
        ensure_aspect_target(aspect)


def ensure_lever_targets() -> None:
    """Look up (or, with sample content on, create) every lever category and target."""
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
