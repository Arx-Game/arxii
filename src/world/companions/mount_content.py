"""Seed content for mount-riding conditions (#1843).

Mounted/Unhorsed are verb-gating flags — other code branches on their
presence (``has_condition``) to gate mount-only verbs (Charge/Joust) and the
unmounted-lance penalty. Neither carries a ``ConditionCheckModifier`` row:
mounting itself grants no passive check bonuses (the spec is explicit about
this — combat advantage comes from the Charge/Joust maneuvers, not from
merely sitting a saddle).
"""

from __future__ import annotations

MOUNTED_CONDITION_NAME = "Mounted"
UNHORSED_CONDITION_NAME = "Unhorsed"


def ensure_mount_conditions() -> None:
    """Idempotently seed the Mounted/Unhorsed ConditionTemplates.

    Mounted: applied by ``mount_companion``, removed by ``dismount_companion``.
    Permanent duration — it persists until a dismount trigger fires (voluntary,
    encounter exit, or the companion's defeat), not until a round timer expires.

    Unhorsed: applied to a joust loser on a decisive-margin result
    (``world.combat.services._resolve_joust_pass``), which force-dismounts the
    rider immediately afterward via a direct ``dismount_companion`` call — no
    reactive trigger is needed since the caller already has both sheets in hand.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415

    category, _ = ConditionCategory.objects.get_or_create(
        name="Mount State",
        defaults={
            "description": "Conditions describing a character's mount-riding state.",
            "is_negative": False,
            "display_order": 50,
        },
    )
    ConditionTemplate.objects.get_or_create(
        name=MOUNTED_CONDITION_NAME,
        defaults={
            "description": (
                "Riding a mount. Gates mount-only verbs (Charge, Joust); grants no "
                "passive check bonuses."
            ),
            "category": category,
            "default_duration_type": DurationType.PERMANENT,
            "default_duration_value": 0,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": False,
        },
    )
    ConditionTemplate.objects.get_or_create(
        name=UNHORSED_CONDITION_NAME,
        defaults={
            "description": "Thrown from the saddle in a joust. Forces an immediate dismount.",
            "category": category,
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 1,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": True,
        },
    )
