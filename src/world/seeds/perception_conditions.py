"""Perception/visibility content seed (#1225) — the Concealed condition primitive.

Seeds a Concealed ConditionCategory (conceals_from_perception=True) and a generic
Concealed ConditionTemplate on it. No automatic application path is built here —
this is deliberately just the seam's one real producer, usable via staff/scripts
today. Stealth witness-reduction (#1464) and the forms disguise-pierce contest are
the deferred automated producers; both apply/clear this same condition once built.

Mirrors the get-or-create pattern in world/magic/effect_palette_content.py's
_seed_intangibility_condition.
"""

from __future__ import annotations

from world.conditions.constants import DurationType


def seed_perception_condition_content() -> None:
    """Cluster entry — seed the Concealed condition category + template."""
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415

    category, _ = ConditionCategory.objects.get_or_create(
        name="Concealed",
        defaults={
            "description": (
                "Conditions that make the bearer imperceptible to others "
                "(invisibility, magical concealment, stealth) — pierced per-observer "
                "via a detection check, never revealed via a check to everyone at once."
            ),
            "is_negative": False,
            "display_order": 40,
            "alters_behavior": False,
            "conceals_from_perception": True,
        },
    )
    ConditionTemplate.objects.get_or_create(
        name="Concealed",
        defaults={
            "description": "The bearer cannot be perceived by anyone who hasn't detected them.",
            "category": category,
            "default_duration_type": DurationType.PERMANENT,
            "default_duration_value": 0,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": True,
        },
    )
