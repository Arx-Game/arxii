"""Conjured Barrier challenge seed (#4606).

A spell-made wall gates its edge with an instance of the "Conjured Barrier"
:class:`~world.mechanics.models.ChallengeTemplate` (``create_obstacle`` mints it by
name), so anyone may climb over or smash through it (ADR-0109). Without the
template a Barricade cast fails, so the row is seeded here and listed on the
Required content dashboard.

Two approaches, each a capability matched to a property the challenge holds:

* **Climb Over** — the ``traversal`` capability against ``elevated`` ("Ascend");
* **Smash Through** — the ``force`` capability against ``breakable`` ("Break").

Both roll the Athletics check the "security" cluster composes. A clean success
resolves the challenge for everyone (DESTROY), which opens the wall: the walker
rule reads an inactive gate as open (``edge_blocks_crossing``).

The challenge, its properties, capabilities, applications and approaches are
content-repo-owned (#2698), so every row is looked up through
``authored_or_sample`` and invented only under ``SEED_SAMPLE_CONTENT``. Safe to
call repeatedly.
"""

from world.areas.positioning.constants import CONJURED_BARRIER_CHALLENGE_NAME
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
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.seeds.sample_content import authored_or_sample
from world.traits.models import CheckOutcome

_BARRIER_SEVERITY: int = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
_BARRIER_CHECK_TYPE_NAME: str = "Athletics"

# (property name, property category, capability, application, approach, fiction)
_BARRIER_APPROACHES: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "elevated",
        "Environmental",
        "traversal",
        "Ascend",
        "Climb Over",
        "You find holds in the conjured wall and haul yourself over the top.",
    ),
    (
        "breakable",
        "Physical",
        "force",
        "Break",
        "Smash Through",
        "You throw your weight against the wall until it gives way.",
    ),
)


def _ensure_destroy_on_success(template: ChallengeTemplate) -> None:
    """Link a SUCCESS-tier DESTROY consequence: getting past opens the wall for all."""
    success, _ = CheckOutcome.objects.get_or_create(
        name="Success",
        defaults={"description": "The action succeeds cleanly.", "success_level": 1},
    )
    consequence, _ = Consequence.objects.get_or_create(
        outcome_tier=success,
        label="The wall is passed",
        defaults={
            "mechanical_description": "The conjured wall no longer bars the way.",
            "weight": 1,
            "character_loss": False,
        },
    )
    ChallengeTemplateConsequence.objects.get_or_create(
        challenge_template=template,
        consequence=consequence,
        defaults={"resolution_type": ResolutionType.DESTROY},
    )


def ensure_conjured_barrier_content() -> None:
    """Idempotently seed the "Conjured Barrier" challenge and its two approaches."""
    category = authored_or_sample(
        ChallengeCategory,
        {"description": "Physical obstacles and structures."},
        name="Physical",
    )
    if category is None:
        return
    template = authored_or_sample(
        ChallengeTemplate,
        {
            "description_template": "A conjured wall bars the way.",
            "severity": _BARRIER_SEVERITY,
            "goal": "Get past the conjured wall.",
            "category": category,
            "challenge_type": ChallengeType.INHIBITOR,
        },
        name=CONJURED_BARRIER_CHALLENGE_NAME,
    )
    if template is None:
        return
    _ensure_destroy_on_success(template)

    check_category = authored_or_sample(CheckCategory, {}, name="Physical")
    check_type = (
        authored_or_sample(CheckType, {}, name=_BARRIER_CHECK_TYPE_NAME, category=check_category)
        if check_category is not None
        else None
    )
    for (
        prop_name,
        prop_category,
        capability_name,
        app_name,
        display,
        fiction,
    ) in _BARRIER_APPROACHES:
        property_category = authored_or_sample(PropertyCategory, {}, name=prop_category)
        if property_category is None:
            continue
        prop = authored_or_sample(Property, {"category": property_category}, name=prop_name)
        if prop is None:
            continue
        # The challenge holds the property so the approach surfaces in
        # _match_approaches (offered iff the challenge carries the target property).
        ChallengeTemplateProperty.objects.get_or_create(
            challenge_template=template, property=prop, defaults={"value": 1}
        )
        capability = authored_or_sample(CapabilityType, {}, name=capability_name)
        if capability is None:
            continue
        application = authored_or_sample(
            Application, {}, name=app_name, capability=capability, target_property=prop
        )
        if application is None or check_type is None:
            continue
        authored_or_sample(
            ChallengeApproach,
            {"check_type": check_type, "display_name": display, "custom_description": fiction},
            challenge_template=template,
            application=application,
        )
