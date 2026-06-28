"""Idempotent seed for Charm/Calm condition content (#1590).

Mirrors ``ensure_poison_content``: ``get_or_create`` the Charm category
(``alters_behavior=True`` — the flag combat consults for allegiance) and the
Charmed/Calm templates. Called at the same startup-seed point as poison.
"""

from __future__ import annotations

from world.conditions.constants import (
    CALM_CONDITION_NAME,
    CHARM_CONDITION_NAME,
    DurationType,
)
from world.conditions.models import ConditionCategory, ConditionTemplate


def ensure_charm_content() -> None:
    """Idempotently seed the Charm category + Charmed/Calm templates (#1590)."""
    category, _ = ConditionCategory.objects.get_or_create(
        name="Charm",
        defaults={
            "description": "Compulsion/charm effects that alter an NPC's behavior.",
            "is_negative": True,
            "alters_behavior": True,
        },
    )
    ConditionTemplate.objects.get_or_create(
        name=CHARM_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "Charmed into fighting for the caster.",
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 3,
            "is_stackable": False,
            "can_be_dispelled": True,
        },
    )
    ConditionTemplate.objects.get_or_create(
        name=CALM_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "Calmed into holding — will not attack.",
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 3,
            "is_stackable": False,
            "can_be_dispelled": True,
        },
    )
