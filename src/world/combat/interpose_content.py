"""Interpose challenge content seed (#1273).

Idempotently seeds the content the interpose feature needs:

* an "Interpose" :class:`~world.mechanics.models.ChallengeTemplate` carrying an
  ``interposable`` :class:`~world.mechanics.models.Property`, four seed
  :class:`~world.conditions.models.CapabilityType` rows (``telekinesis`` is the
  shared row also seeded by the catch content — ``get_or_create`` ensures a single
  row), one :class:`~world.mechanics.models.Application` +
  :class:`~world.mechanics.models.ChallengeApproach` per capability (Reflexes
  :class:`~world.checks.models.CheckType`, same as the catch challenge), and a
  SUCCESS-tier DESTROY consequence (clean block).

``ensure_interpose_content`` mirrors
``world.areas.positioning.plummet_content.ensure_catch_content`` and is safe to call
repeatedly: every write goes through ``get_or_create``. It
doubles as integration-test setup and staff seed data.
"""

from world.areas.positioning.constants import CATCH_CHECK_TYPE_NAME
from world.checks.models import CheckCategory, CheckType, Consequence
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
from world.traits.models import CheckOutcome

# ---------------------------------------------------------------------------
# Identity keys
# ---------------------------------------------------------------------------

INTERPOSE_CHALLENGE_NAME: str = "Interpose"
INTERPOSABLE_PROPERTY_NAME: str = "interposable"

# Authored difficulty of the interpose challenge. Lives on
# ChallengeTemplate.severity — never as a literal target_difficulty in engine code.
_INTERPOSE_SEVERITY: int = 3

# Seed interpose capabilities. Each entry:
#   (capability_name, application_name, display_name, fiction)
# Adding a new interpose capability later is pure data: append a tuple here (or,
# at runtime, insert one CapabilityType + Application(target_property=interposable
# property) + ChallengeApproach row), with zero engine code.
_INTERPOSE_CAPABILITIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "telekinesis",
        "Interpose by Telekinesis",
        "Telekinetic Guard",
        "You wrench the blow aside with unseen force before it lands.",
    ),
    (
        "shield",
        "Interpose by Shield",
        "Shield Wall",
        "You thrust your shield between the attacker and your ally, absorbing the strike.",
    ),
    (
        "barrier",
        "Interpose by Barrier",
        "Conjured Barrier",
        "You raise a conjured barrier in the blow's path, turning it aside.",
    ),
    (
        "pull_aside",
        "Interpose by Pull",
        "Protective Pull",
        "You seize your ally and haul them clear of the incoming strike at the last instant.",
    ),
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _ensure_interpose_property() -> Property:
    """Idempotently seed the shared 'interposable' target Property.

    Every interpose Application addresses this single Property; the challenge
    template carries it too so its approaches surface in ``_match_approaches``
    (which gates an approach on the challenge holding the Application's target
    property).
    """
    category, _ = PropertyCategory.objects.get_or_create(
        name="Physical",
        defaults={"description": "Physical state of a target or environment."},
    )
    obj, _ = Property.objects.get_or_create(
        name=INTERPOSABLE_PROPERTY_NAME,
        defaults={
            "description": "A character positioned to take a blow on behalf of an ally.",
            "category": category,
        },
    )
    return obj


def _ensure_interpose_check_type() -> CheckType:
    """Idempotently seed the Reflexes CheckType reused by every interpose approach.

    Reuses the same CheckType row as the catch challenge (CATCH_CHECK_TYPE_NAME ==
    'Reflexes'). A split-second reaction is the shared mechanical fiction whether
    you're catching a faller or stepping in front of a blow.
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


def _ensure_clean_interpose_consequence(template: ChallengeTemplate) -> None:
    """Idempotently link a SUCCESS-tier DESTROY consequence to the template.

    A clean block resolves the challenge for everyone (DESTROY) — Task resolution
    reads this to end the interpose. PARTIAL/FAILURE tiers are intentionally
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
        label="Clean block",
        defaults={
            "mechanical_description": "The blow is turned aside and the interpose ends.",
            "weight": 1,
            "character_loss": False,
        },
    )
    ChallengeTemplateConsequence.objects.get_or_create(
        challenge_template=template,
        consequence=consequence,
        defaults={"resolution_type": ResolutionType.DESTROY},
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ensure_interpose_content() -> None:
    """Idempotently seed the "Interpose" challenge (#1273).

    Seeds the four seed interpose ``CapabilityType`` rows (``telekinesis`` reuses
    the shared row from the catch content — ``get_or_create`` by name), the shared
    ``interposable`` ``Property``, the reused Reflexes ``CheckType``, the
    capability-gated ``ChallengeTemplate`` (with authored severity), one
    ``Application`` + ``ChallengeApproach`` per capability, and a SUCCESS-tier
    DESTROY consequence so a clean block resolves the challenge. Safe to call
    repeatedly — every write goes through ``get_or_create``.

    Adding a new interpose capability later is pure data: a new
    ``CapabilityType`` + ``Application(target_property=interpose property)`` +
    ``ChallengeApproach`` row surfaces with no engine change.
    """
    interpose_property = _ensure_interpose_property()
    check_type = _ensure_interpose_check_type()

    challenge_category, _ = ChallengeCategory.objects.get_or_create(
        name="Environmental",
        defaults={"description": "Hazards arising from the surroundings."},
    )
    template, _ = ChallengeTemplate.objects.get_or_create(
        name=INTERPOSE_CHALLENGE_NAME,
        defaults={
            "description_template": (
                "{interposer} moves to shield {ally} — someone with the means may "
                "attempt to turn the blow aside."
            ),
            "severity": _INTERPOSE_SEVERITY,
            "goal": "Turn aside the blow before it reaches the protected ally.",
            "category": challenge_category,
            "challenge_type": ChallengeType.THREAT,
        },
    )

    # The challenge holds the interposable property so its approaches surface in
    # _match_approaches (an approach is offered iff the challenge carries the
    # Application's target property).
    ChallengeTemplateProperty.objects.get_or_create(
        challenge_template=template,
        property=interpose_property,
        defaults={"value": 1},
    )

    _ensure_clean_interpose_consequence(template)

    for capability_name, application_name, display_name, fiction in _INTERPOSE_CAPABILITIES:
        capability, _ = CapabilityType.objects.get_or_create(name=capability_name)
        application, _ = Application.objects.get_or_create(
            name=application_name,
            defaults={
                "capability": capability,
                "target_property": interpose_property,
                "description": f"Interpose on behalf of an ally using {capability_name}.",
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
