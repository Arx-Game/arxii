"""Intoxication + hangover condition content (#2852).

The classic MUD drunk loop as staged conditions (mirrors ``ensure_poison_content``'s
shape): ``Intoxicated`` climbs severity-threshold stages drink by drink (the
``INTOXICATE`` consequence effect advances it), wears off on the IC clock, and past
the Blackout threshold each further drink risks a stamina pass-out — the existing
``Unconscious`` machinery (wake rolls, deadlines) handles the rest. ``Hungover``
lands alongside a pass-out and carries a willpower penalty — which is exactly what
the moon impairment predicate (#2845) reads, so a hungover high-tier lycan is
checkable again with zero extra wiring.

All magnitudes PLACEHOLDER (#2852 author pass). Addiction is the ruled deeper
layer — deliberately not built here; drugs ride the same INTOXICATE seam as
future content.
"""

from __future__ import annotations

INTOXICATED_CONDITION_NAME = "Intoxicated"
HUNGOVER_CONDITION_NAME = "Hungover"

# Severity thresholds for the stages (PLACEHOLDER).
TIPSY_THRESHOLD = 1
DRUNK_THRESHOLD = 3
SODDEN_THRESHOLD = 5
BLACKOUT_THRESHOLD = 7

# Past this severity, every further drink rolls the stamina pass-out check.
PASS_OUT_SEVERITY_THRESHOLD = BLACKOUT_THRESHOLD
PASS_OUT_BASE_DIFFICULTY = 10
PASS_OUT_DIFFICULTY_PER_SEVERITY = 5

# IC hours before the conditions wear off (INGAME_TIME duration values).
INTOXICATED_IC_HOURS = 8
HUNGOVER_IC_HOURS = 16

# Hungover willpower penalty (ConditionModifierEffect on the willpower stat
# target) — one tier down feeds the #2845 moon impairment predicate.
HUNGOVER_WILLPOWER_PENALTY = -10


def ensure_intoxication_content() -> None:
    """Idempotently seed the Intoxicated + Hungover condition content."""
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import (  # noqa: PLC0415
        ConditionCategory,
        ConditionStage,
        ConditionTemplate,
    )

    category, _ = ConditionCategory.objects.get_or_create(
        name="Intoxication",
        defaults={
            "description": "Drink and drug states — impairing, social, self-inflicted.",
            "is_negative": True,
        },
    )
    intoxicated, _ = ConditionTemplate.objects.get_or_create(
        name=INTOXICATED_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "PLACEHOLDER: drink warming the blood and loosening the tongue.",
            "player_description": "The drink has its hooks in you.",
            "observer_description": "is visibly the worse for drink.",
            "default_duration_type": DurationType.INGAME_TIME,
            "default_duration_value": INTOXICATED_IC_HOURS,
            "has_progression": True,
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    stages = (
        (1, "Tipsy", TIPSY_THRESHOLD, "PLACEHOLDER: warm, loose, a little loud."),
        (2, "Drunk", DRUNK_THRESHOLD, "PLACEHOLDER: slurring, swaying, sure of everything."),
        (3, "Sodden", SODDEN_THRESHOLD, "PLACEHOLDER: the room tilts; words desert you."),
        (4, "Blackout", BLACKOUT_THRESHOLD, "PLACEHOLDER: the night is a hole with your name."),
    )
    for order, name, threshold, desc in stages:
        ConditionStage.objects.get_or_create(
            condition=intoxicated,
            stage_order=order,
            defaults={
                "name": name,
                "description": desc,
                "severity_threshold": threshold,
                "severity_multiplier": "1.00",
            },
        )
    hungover, _ = ConditionTemplate.objects.get_or_create(
        name=HUNGOVER_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "PLACEHOLDER: the morning's bill for the night's grandeur.",
            "player_description": "Your skull is two sizes too small and full of sand.",
            "observer_description": "is grey-faced and wincing at the light.",
            "default_duration_type": DurationType.INGAME_TIME,
            "default_duration_value": HUNGOVER_IC_HOURS,
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    _ensure_hungover_willpower_penalty(hungover)


def _ensure_hungover_willpower_penalty(hungover) -> None:
    """Willpower penalty on Hungover — the #2845 impairment predicate's food."""
    from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    trait = Trait.objects.filter(name="willpower", trait_type=TraitType.STAT).first()
    if trait is None:
        return
    mod_category, _ = ModifierCategory.objects.get_or_create(
        name="stat", defaults={"description": "Stat modifiers."}
    )
    target, _ = ModifierTarget.objects.get_or_create(
        name="willpower",
        category=mod_category,
        defaults={"target_trait": trait},
    )
    if target.target_trait_id is None:
        target.target_trait = trait
        target.save(update_fields=["target_trait"])
    ConditionModifierEffect.objects.get_or_create(
        condition=hungover,
        modifier_target=target,
        defaults={"value": HUNGOVER_WILLPOWER_PENALTY, "scales_with_severity": False},
    )
