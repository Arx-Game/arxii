"""Plummet content seed (#1228).

Idempotently seeds the content the reactive-catch / plummet feature needs:

* a ``Fall`` :class:`~world.conditions.models.DamageType` (impact damage at the
  bottom of a fall), with null wound/death pools so the config-default
  survivability pools apply — exactly like the poison/exhaustion DamageTypes; and
* a staged "Plummeting" :class:`~world.conditions.models.ConditionTemplate` whose
  stages model descent-depth bands (deeper fall → higher severity multiplier),
  advancing one stage per round (the descent cadence).

The Plummeting condition has **no** ``ConditionDamageOverTime`` row — the impact
is applied explicitly when the fall ends (Task 6), not as per-round damage.

``ensure_fall_content`` mirrors ``world.conditions.services.ensure_poison_content``
and is safe to call repeatedly: every write goes through ``get_or_create``. It
doubles as integration-test setup and staff seed data.
"""

from decimal import Decimal

from world.areas.positioning.constants import (
    FALL_DAMAGE_TYPE_NAME,
    FALLING_CATEGORY_NAME,
    PLUMMETING_CONDITION_NAME,
)
from world.conditions.constants import DurationType
from world.conditions.models import (
    ConditionCategory,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)


def _ensure_falling_category() -> ConditionCategory:
    """Idempotently seed the Falling ConditionCategory.

    ConditionTemplate.category is a non-null PROTECT FK, so the Plummeting
    template needs a stable category row to point at.
    """
    obj, _ = ConditionCategory.objects.get_or_create(
        name=FALLING_CATEGORY_NAME,
        defaults={
            "description": "Uncontrolled descent through the air toward an impact.",
            "is_negative": True,
        },
    )
    return obj


def _ensure_fall_damage_type() -> DamageType:
    """Idempotently seed the fall-impact DamageType.

    Leaves the consequence pools null so the config-default survivability
    fallback applies (the same idiom as the poison/exhaustion DamageTypes).
    """
    obj, _ = DamageType.objects.get_or_create(
        name=FALL_DAMAGE_TYPE_NAME,
        defaults={
            "description": "Blunt impact damage from striking the ground after a fall.",
        },
    )
    return obj


# Descent-depth stage bands for the Plummeting condition. Each entry is one
# stage: a deeper fall reached on a later round, with a higher severity
# multiplier feeding the eventual impact. ``rounds_to_next=1`` advances one
# stage per round (the descent cadence); the terminal stage advances no further.
_PLUMMET_STAGES: tuple[tuple[str, str, str], ...] = (
    (
        "Tipping Over",
        "The first sickening lurch as footing is lost and the ground falls away.",
        "1.00",
    ),
    (
        "Gathering Speed",
        "The plunge accelerates; the world rushes upward.",
        "1.50",
    ),
    (
        "Terminal Plunge",
        "A headlong fall from a killing height, an instant from impact.",
        "2.00",
    ),
)


def ensure_fall_content() -> None:
    """Idempotently seed the plummet content (#1228).

    Seeds the Falling category, the fall-impact DamageType, and the staged
    Plummeting ConditionTemplate (descent-depth severity stages, no DoT). Safe
    to call repeatedly — every write goes through get_or_create.
    """
    category = _ensure_falling_category()
    _ensure_fall_damage_type()

    plummeting, _ = ConditionTemplate.objects.get_or_create(
        name=PLUMMETING_CONDITION_NAME,
        defaults={
            "category": category,
            "description": (
                "A character is falling through the air, descending deeper each "
                "round until impact at the bottom."
            ),
            "has_progression": True,
            "is_stackable": False,
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": len(_PLUMMET_STAGES),
        },
    )

    last_index = len(_PLUMMET_STAGES) - 1
    for index, (name, description, multiplier) in enumerate(_PLUMMET_STAGES):
        ConditionStage.objects.get_or_create(
            condition=plummeting,
            stage_order=index + 1,
            defaults={
                "name": name,
                "description": description,
                "rounds_to_next": None if index == last_index else 1,
                "severity_multiplier": Decimal(multiplier),
            },
        )
