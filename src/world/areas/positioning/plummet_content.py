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
    ACROBATICS_CAPABILITY_NAME,
    CATCH_CHECK_TYPE_NAME,
    CATCH_THE_FALLER_NAME,
    CATCHABLE_PROPERTY_NAME,
    FALL_DAMAGE_TYPE_NAME,
    FALLING_CATEGORY_NAME,
    FLY_CAPABILITY_NAME,
    PLUMMETING_CONDITION_NAME,
    TELEKINESIS_CAPABILITY_NAME,
    TELEPORT_CAPABILITY_NAME,
)
from world.checks.models import CheckCategory, CheckType, Consequence
from world.conditions.constants import DurationType
from world.conditions.models import (
    CapabilityType,
    ConditionCategory,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)
from world.mechanics.constants import ChallengeType, ResolutionType
from world.mechanics.models import (
    Application,
    ChallengeApproach,
    ChallengeCategory,
    ChallengeTemplate,
    ChallengeTemplateConsequence,
    ChallengeTemplateProperty,
    Property,
    PropertyCategory,
)
from world.traits.models import CheckOutcome


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
    ensure_catch_content()

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


# ---------------------------------------------------------------------------
# "Catch the Faller" capability-gated catch challenge (#1228, Task 4)
# ---------------------------------------------------------------------------

# Authored difficulty of the catch challenge. Difficulty lives on the
# ChallengeTemplate.severity row (this constant feeds that authored field) —
# never as a literal target_difficulty in engine code.
_CATCH_SEVERITY: int = 3

# Seed catch capabilities. Each entry: (capability name, Application name,
# approach display_name, approach fiction). The named four are SEED EXAMPLES —
# adding a fifth is pure data: append a tuple here (or, at runtime, insert one
# CapabilityType + Application(target_property=catch property) + ChallengeApproach
# row), with zero engine code. Every Application shares the one catch Property,
# and every approach reuses the one Reflexes CheckType.
_CATCH_CAPABILITIES: tuple[tuple[str, str, str, str], ...] = (
    (
        FLY_CAPABILITY_NAME,
        "Catch in Flight",
        "Flight Intercept",
        "You dive on beating wings, matching the plunge to pluck the faller out of the air.",
    ),
    (
        TELEPORT_CAPABILITY_NAME,
        "Catch by Teleport",
        "Translocated Catch",
        "You blink into the falling body's path and close your arms around them mid-air.",
    ),
    (
        TELEKINESIS_CAPABILITY_NAME,
        "Catch by Telekinesis",
        "Telekinetic Arrest",
        "From afar, you seize the plunging figure with unseen force and ease their descent.",
    ),
    (
        ACROBATICS_CAPABILITY_NAME,
        "Catch by Acrobatics",
        "Acrobatic Save",
        "You vault, twist, and snatch the faller from the edge of the drop with raw agility.",
    ),
)


def _ensure_catch_property() -> Property:
    """Idempotently seed the shared 'catchable' target Property.

    Every catch Application addresses this single Property; the challenge
    template carries it too so its approaches surface in ``_match_approaches``
    (which gates an approach on the challenge holding the Application's target
    property).
    """
    category, _ = PropertyCategory.objects.get_or_create(
        name="Physical",
        defaults={"description": "Physical state of a target or environment."},
    )
    obj, _ = Property.objects.get_or_create(
        name=CATCHABLE_PROPERTY_NAME,
        defaults={
            "description": "A falling body that another character may attempt to catch.",
            "category": category,
        },
    )
    return obj


def _ensure_catch_check_type() -> CheckType:
    """Idempotently seed the Reflexes CheckType reused by every catch approach.

    A single shared check type — the fiction differs per capability, but the
    mechanical roll (split-second reaction) is the same, so no per-capability
    CheckType is authored.
    """
    category, _ = CheckCategory.objects.get_or_create(name="Exploration")
    obj, _ = CheckType.objects.get_or_create(
        name=CATCH_CHECK_TYPE_NAME,
        category=category,
        defaults={
            "description": "A split-second reaction to arrest a falling body.",
        },
    )
    return obj


def _ensure_clean_catch_consequence(template: ChallengeTemplate) -> None:
    """Idempotently link a SUCCESS-tier DESTROY consequence to the template.

    A clean catch resolves the challenge for everyone (DESTROY) — Task 7 reads
    the resolution to end the plummet. PARTIAL/FAILURE tiers are intentionally
    omitted: ``resolve_challenge`` supplies a synthetic fallback for any tier
    without an authored consequence.
    """
    success, _ = CheckOutcome.objects.get_or_create(
        name="Success",
        defaults={
            "description": "The action succeeds cleanly.",
            "success_level": 1,
        },
    )
    consequence, _ = Consequence.objects.get_or_create(
        outcome_tier=success,
        label="Clean catch",
        defaults={
            "mechanical_description": "The faller is caught and the plummet ends.",
            "weight": 1,
            "character_loss": False,
        },
    )
    ChallengeTemplateConsequence.objects.get_or_create(
        challenge_template=template,
        consequence=consequence,
        defaults={"resolution_type": ResolutionType.DESTROY},
    )


def ensure_catch_content() -> None:
    """Idempotently seed the "Catch the Faller" challenge (#1228, Task 4).

    Seeds the four seed catch ``CapabilityType`` rows, the shared catch
    ``Property``, the reused Reflexes ``CheckType``, the capability-gated
    ``ChallengeTemplate`` (with authored severity), one ``Application`` +
    ``ChallengeApproach`` per capability, and a SUCCESS-tier DESTROY consequence
    so a clean catch resolves the challenge. Safe to call repeatedly — every
    write goes through ``get_or_create``.

    Adding a new catch capability later is pure data: a new
    ``CapabilityType`` + ``Application(target_property=catch property)`` +
    ``ChallengeApproach`` row surfaces with no engine change.
    """
    catch_property = _ensure_catch_property()
    check_type = _ensure_catch_check_type()

    challenge_category, _ = ChallengeCategory.objects.get_or_create(
        name="Environmental",
        defaults={"description": "Hazards arising from the surroundings."},
    )
    template, _ = ChallengeTemplate.objects.get_or_create(
        name=CATCH_THE_FALLER_NAME,
        defaults={
            "description_template": (
                "{faller} is plummeting — someone with the means may try to "
                "catch them before they strike the ground."
            ),
            "severity": _CATCH_SEVERITY,
            "goal": "Catch the falling character before impact.",
            "category": challenge_category,
            "challenge_type": ChallengeType.THREAT,
        },
    )

    # The challenge holds the catch property so its approaches surface in
    # _match_approaches (an approach is offered iff the challenge carries the
    # Application's target property).
    ChallengeTemplateProperty.objects.get_or_create(
        challenge_template=template,
        property=catch_property,
        defaults={"value": 1},
    )

    _ensure_clean_catch_consequence(template)

    for capability_name, application_name, display_name, fiction in _CATCH_CAPABILITIES:
        capability, _ = CapabilityType.objects.get_or_create(name=capability_name)
        application, _ = Application.objects.get_or_create(
            name=application_name,
            defaults={
                "capability": capability,
                "target_property": catch_property,
                "description": f"Catch a falling character using {capability_name}.",
            },
        )
        ChallengeApproach.objects.get_or_create(
            challenge_template=template,
            application=application,
            defaults={
                "check_type": check_type,
                "display_name": display_name,
                "custom_description": fiction,
            },
        )
