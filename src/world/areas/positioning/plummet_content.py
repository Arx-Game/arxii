"""Plummet content seed (#1228).

Idempotently seeds the content the reactive-catch / plummet feature needs:

* a ``Fall`` :class:`~world.conditions.models.DamageType` (impact damage at the
  bottom of a fall), with null wound/death pools so the config-default
  survivability pools apply — exactly like the poison/exhaustion DamageTypes; and
* a simple non-expiring "Plummeting" :class:`~world.conditions.models.ConditionTemplate`
  marker. It carries **no** stages and a ``PERMANENT`` duration so the descent
  loop alone owns its lifetime: ``advance_plummet`` removes it on impact and
  ``end_plummet`` removes it on a clean catch — it never auto-expires mid-air.

Descent depth is tracked solely by the condition instance's per-round
``severity`` accumulator (``advance_plummet`` does ``severity += 1`` per level
descended), which then feeds the impact: ``damage = severity *
FALL_IMPACT_PER_LEVEL``. There is no stage ``severity_multiplier`` — the raw
accumulator is the depth.

The Plummeting condition has **no** ``ConditionDamageOverTime`` row — the impact
is applied explicitly when the fall ends (Task 6), not as per-round damage.

``ensure_fall_content`` mirrors ``world.conditions.services.ensure_poison_content``
and is safe to call repeatedly: every write goes through ``get_or_create``. It
doubles as integration-test setup and staff seed data.
"""

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
from world.seeds.sample_content import authored_or_sample
from world.traits.models import CheckOutcome


def _ensure_falling_category() -> ConditionCategory | None:
    """Idempotently seed the Falling ConditionCategory.

    ConditionTemplate.category is a non-null PROTECT FK, so the Plummeting
    template needs a stable category row to point at. Content-repo-owned
    (#2698) — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    """
    return authored_or_sample(
        ConditionCategory,
        {
            "description": "Uncontrolled descent through the air toward an impact.",
            "is_negative": True,
        },
        name=FALLING_CATEGORY_NAME,
    )


def _ensure_fall_damage_type() -> DamageType | None:
    """Idempotently seed the fall-impact DamageType.

    Leaves the consequence pools null so the config-default survivability
    fallback applies (the same idiom as the poison/exhaustion DamageTypes).
    Content-repo-owned (#2698) — looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on.
    """
    return authored_or_sample(
        DamageType,
        {"description": "Blunt impact damage from striking the ground after a fall."},
        name=FALL_DAMAGE_TYPE_NAME,
    )


def ensure_fall_content() -> None:
    """Idempotently seed the plummet content (#1228).

    Seeds the Falling category, the fall-impact DamageType, and the Plummeting
    ConditionTemplate as a simple non-expiring marker (no stages, no DoT). The
    descent loop alone owns the condition's lifetime — a ``PERMANENT`` duration
    means it never auto-expires mid-air, so deep falls always reach impact. Safe
    to call repeatedly — every write goes through get_or_create.
    """
    category = _ensure_falling_category()
    _ensure_fall_damage_type()
    ensure_catch_content()

    authored_or_sample(
        ConditionTemplate,
        {
            "category": category,
            "description": (
                "A character is falling through the air, descending deeper each "
                "round until impact at the bottom."
            ),
            # Non-progressive, non-expiring marker: depth lives in the instance's
            # per-round ``severity`` accumulator, and only advance_plummet /
            # end_plummet remove it. PERMANENT leaves rounds_remaining=None so the
            # end-of-round duration countdown never expires it before the descent
            # loop reaches the floor.
            "has_progression": False,
            "is_stackable": False,
            "default_duration_type": DurationType.PERMANENT,
        },
        name=PLUMMETING_CONDITION_NAME,
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


def _ensure_catch_property() -> Property | None:
    """Idempotently look up the shared 'catchable' target Property.

    Every catch Application addresses this single Property; the challenge
    template carries it too so its approaches surface in ``_match_approaches``
    (which gates an approach on the challenge holding the Application's target
    property). mechanics.Property/PropertyCategory are content-repo-owned
    (#2698) — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    """
    category = authored_or_sample(
        PropertyCategory,
        {"description": "Physical state of a target or environment."},
        name="Physical",
    )
    return authored_or_sample(
        Property,
        {
            "description": "A falling body that another character may attempt to catch.",
            "category": category,
        },
        name=CATCHABLE_PROPERTY_NAME,
    )


def _ensure_catch_check_type() -> CheckType:
    """Idempotently seed the Reflexes CheckType reused by every catch approach.

    A single shared check type — the fiction differs per capability, but the
    mechanical roll (split-second reaction) is the same, so no per-capability
    CheckType is authored. The single ``wits`` stat leg is the tenet-permitted
    resist composition (#1706); idempotent ``get_or_create`` preserves any
    existing staff weight edit. Shared by plummet-catch and interpose (both
    ``get_or_create`` this row).
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import CheckTypeTrait  # noqa: PLC0415
    from world.traits.factories import StatTraitFactory  # noqa: PLC0415
    from world.traits.models import TraitCategory  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(name="Exploration")
    obj, _ = CheckType.objects.get_or_create(
        name=CATCH_CHECK_TYPE_NAME,
        category=category,
        defaults={
            "description": "A split-second reaction to arrest a falling body.",
        },
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=obj,
        trait=StatTraitFactory(name="wits", category=TraitCategory.MENTAL),
        defaults={"weight": Decimal("1.00")},
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

    ``mechanics.Property``/``PropertyCategory``/``ChallengeCategory``/
    ``ChallengeTemplate``/``Application``/``ChallengeApproach`` are all
    content-repo-owned (#2698) — looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. The whole challenge is skipped when the
    anchor Property or ChallengeCategory/ChallengeTemplate aren't authored —
    there is nothing left to hang approaches on.
    """
    catch_property = _ensure_catch_property()
    if catch_property is None:
        return
    check_type = _ensure_catch_check_type()

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
                "{faller} is plummeting — someone with the means may try to "
                "catch them before they strike the ground."
            ),
            "severity": _CATCH_SEVERITY,
            "goal": "Catch the falling character before impact.",
            "category": challenge_category,
            "challenge_type": ChallengeType.THREAT,
        },
        name=CATCH_THE_FALLER_NAME,
    )
    if template is None:
        return

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
                "target_property": catch_property,
                "description": f"Catch a falling character using {capability_name}.",
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
