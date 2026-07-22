"""Succor challenge content seed (#1744).

Idempotently seeds the content Succor needs: a "Succor" ChallengeTemplate carrying a
sheltering-capable target Property, reusing the same four capability rows Interpose
seeds (telekinesis/shield/barrier/pull_aside — "protecting someone bodily" spans both
an incoming blow and an environmental hazard; no new capability taxonomy needed), one
Application + ChallengeApproach per capability, and a SUCCESS-tier DESTROY consequence.

Mirrors world.combat.interpose_content.ensure_interpose_content exactly. Like the
whole reactive-challenge content family (interpose/catch/redirect siblings), this
is seeded in production by the ``reactive_challenges`` cluster in
``world.seeds.clusters`` (#2636) and also remains directly callable as
integration-test setup or from the evennia shell.
"""

from world.checks.models import CheckCategory, CheckType, Consequence
from world.combat.interpose_content import CATCH_CHECK_TYPE_NAME
from world.conditions.models import CapabilityType
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
from world.mechanics.succor_shared import SUCCOR_CHALLENGE_NAME
from world.traits.models import CheckOutcome

SUCCORABLE_PROPERTY_NAME: str = "succorable"

_SUCCOR_SEVERITY: int = 3

_SUCCOR_CAPABILITIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "telekinesis",
        "Succor by Telekinesis",
        "Telekinetic Shelter",
        "You bend unseen force into a shield against the hazard bearing down on your ally.",
    ),
    (
        "shield",
        "Succor by Shield",
        "Shield Shelter",
        "You angle your shield to shelter your ally from the elements.",
    ),
    (
        "barrier",
        "Succor by Barrier",
        "Conjured Shelter",
        "You raise a conjured barrier between your ally and the hazard.",
    ),
    (
        "pull_aside",
        "Succor by Pull",
        "Protective Pull",
        "You haul your ally into shelter before the hazard reaches them.",
    ),
)


def _ensure_succorable_property() -> Property:
    category, _ = PropertyCategory.objects.get_or_create(
        name="Physical",
        defaults={"description": "Physical state of a target or environment."},
    )
    obj, _ = Property.objects.get_or_create(
        name=SUCCORABLE_PROPERTY_NAME,
        defaults={
            "description": "A character sheltered from an environmental hazard by an ally.",
            "category": category,
        },
    )
    return obj


def _ensure_succor_check_type() -> CheckType:
    category, _ = CheckCategory.objects.get_or_create(name="Exploration")
    obj, _ = CheckType.objects.get_or_create(
        name=CATCH_CHECK_TYPE_NAME,
        category=category,
        defaults={"description": "A split-second reaction to shelter someone from harm."},
    )
    return obj


def _ensure_clean_succor_consequence(template: ChallengeTemplate) -> None:
    success, _ = CheckOutcome.objects.get_or_create(
        name="Success",
        defaults={"description": "The action succeeds cleanly.", "success_level": 1},
    )
    consequence, _ = Consequence.objects.get_or_create(
        outcome_tier=success,
        label="Clean shelter",
        defaults={
            "mechanical_description": "The hazard is turned aside and the Succor holds.",
            "weight": 1,
            "character_loss": False,
        },
    )
    ChallengeTemplateConsequence.objects.get_or_create(
        challenge_template=template,
        consequence=consequence,
        defaults={"resolution_type": ResolutionType.DESTROY},
    )


def ensure_succor_content() -> None:
    """Idempotently seed the "Succor" challenge (#1744). Safe to call repeatedly."""
    succorable_property = _ensure_succorable_property()
    check_type = _ensure_succor_check_type()

    challenge_category, _ = ChallengeCategory.objects.get_or_create(
        name="Environmental",
        defaults={"description": "Hazards arising from the surroundings."},
    )
    template, _ = ChallengeTemplate.objects.get_or_create(
        name=SUCCOR_CHALLENGE_NAME,
        defaults={
            "description_template": (
                "{succorer} moves to shelter {ally} — someone with the means may attempt "
                "to turn the hazard aside."
            ),
            "severity": _SUCCOR_SEVERITY,
            "goal": "Shelter the protected ally from the hazard this round.",
            "category": challenge_category,
            "challenge_type": ChallengeType.THREAT,
        },
    )
    ChallengeTemplateProperty.objects.get_or_create(
        challenge_template=template,
        property=succorable_property,
        defaults={"value": 1},
    )
    _ensure_clean_succor_consequence(template)

    for capability_name, application_name, display_name, fiction in _SUCCOR_CAPABILITIES:
        capability, _ = CapabilityType.objects.get_or_create(name=capability_name)
        application, _ = Application.objects.get_or_create(
            name=application_name,
            defaults={
                "capability": capability,
                "target_property": succorable_property,
                "description": f"Succor an ally against a hazard using {capability_name}.",
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
