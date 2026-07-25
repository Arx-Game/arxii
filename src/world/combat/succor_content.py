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
from world.seeds.sample_content import authored_or_sample
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


def _ensure_succorable_property() -> Property | None:
    """Idempotently look up the shared 'succorable' target Property.

    mechanics.Property/PropertyCategory are content-repo-owned (#2698) —
    looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    """
    category = authored_or_sample(
        PropertyCategory,
        {"description": "Physical state of a target or environment."},
        name="Physical",
    )
    return authored_or_sample(
        Property,
        {
            "description": "A character sheltered from an environmental hazard by an ally.",
            "category": category,
        },
        name=SUCCORABLE_PROPERTY_NAME,
    )


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
    """Idempotently seed the "Succor" challenge (#1744). Safe to call repeatedly.

    ``mechanics.Property``/``PropertyCategory``/``ChallengeCategory``/
    ``ChallengeTemplate``/``Application``/``ChallengeApproach`` are all
    content-repo-owned (#2698) — looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. The whole challenge is skipped when the
    anchor Property or ChallengeCategory/ChallengeTemplate aren't authored.
    """
    succorable_property = _ensure_succorable_property()
    if succorable_property is None:
        return
    check_type = _ensure_succor_check_type()

    challenge_category = authored_or_sample(
        ChallengeCategory,
        {"description": "Hazards arising from the surroundings."},
        name="Environmental",
    )
    if challenge_category is None:
        return
    template = authored_or_sample(
        ChallengeTemplate,
        {
            "description_template": (
                "{succorer} moves to shelter {ally} — someone with the means may attempt "
                "to turn the hazard aside."
            ),
            "severity": _SUCCOR_SEVERITY,
            "goal": "Shelter the protected ally from the hazard this round.",
            "category": challenge_category,
            "challenge_type": ChallengeType.THREAT,
        },
        name=SUCCOR_CHALLENGE_NAME,
    )
    if template is None:
        return
    ChallengeTemplateProperty.objects.get_or_create(
        challenge_template=template,
        property=succorable_property,
        defaults={"value": 1},
    )
    _ensure_clean_succor_consequence(template)

    for capability_name, application_name, display_name, fiction in _SUCCOR_CAPABILITIES:
        # conditions.CapabilityType is content-repo-owned (#2698) — looked up
        # rather than invented unless SEED_SAMPLE_CONTENT is on. Skip this
        # capability's approach entirely when it isn't authored.
        capability = authored_or_sample(CapabilityType, {}, name=capability_name)
        if capability is None:
            continue
        application = authored_or_sample(
            Application,
            {
                "capability": capability,
                "target_property": succorable_property,
                "description": f"Succor an ally against a hazard using {capability_name}.",
            },
            name=application_name,
        )
        if application is None:
            continue
        authored_or_sample(
            ChallengeApproach,
            {
                "check_type": check_type,
                "display_name": display_name,
                "custom_description": fiction,
            },
            challenge_template=template,
            application=application,
        )
