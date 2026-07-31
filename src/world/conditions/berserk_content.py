"""Production Berserk condition content (#2845, ADR-0171 config rows).

Berserk is resolved BY NAME at runtime by every producer — the fury engine
(`world.magic.services.fury.run_fury_for_action`) and the moon control check
(`world.species.moon_sensitivity`) — so the row is load-bearing config, not
optional content. Until #2845 it existed only as a test factory
(`world.magic.factories.BerserkConditionTemplateFactory`, whose shape this
seed mirrors exactly) plus a gitignored local fixture whose copy sits in an
`alters_behavior=False` category and would silently fail to block form-revert.

`ensure_berserk_content` therefore also HEALS a pre-existing row: whatever
category a hand-loaded Berserk row landed in, it is re-anchored onto the
Control category so `CharacterSheet.in_control` derives False while raging.
"""

from __future__ import annotations

BERSERK_CONDITION_NAME = "Berserk"
CONTROL_CATEGORY_NAME = "Control"


def ensure_berserk_content() -> None:
    """Idempotently seed (and heal) the Control category + Berserk template."""
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import (  # noqa: PLC0415
        ConditionCategory,
        ConditionStage,
        ConditionTemplate,
    )

    category, _ = ConditionCategory.objects.get_or_create(
        name=CONTROL_CATEGORY_NAME,
        defaults={
            "description": (
                "Conditions that change how a character behaves — compulsion, "
                "charm, fear, rage — rather than only their capabilities or stats."
            ),
            "is_negative": True,
            "alters_behavior": True,
            "display_order": 20,
        },
    )
    if not category.alters_behavior:
        category.alters_behavior = True
        category.save(update_fields=["alters_behavior"])

    template, _ = ConditionTemplate.objects.get_or_create(
        name=BERSERK_CONDITION_NAME,
        defaults={
            "category": category,
            "description": (
                "Lost to primal rage — unable to distinguish friend from foe, "
                "and unable to let go of the shape the rage wears."
            ),
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 3,
            "has_progression": True,
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    if template.category_id != category.pk:
        template.category = category
        template.save(update_fields=["category"])

    ConditionStage.objects.get_or_create(
        condition=template,
        stage_order=1,
        defaults={
            "name": "Uncontrolled Rage",
            "description": (
                "Consumed by uncontrolled rage, lashing out at any target within reach."
            ),
            "rounds_to_next": None,
            "severity_multiplier": "1.00",
        },
    )
