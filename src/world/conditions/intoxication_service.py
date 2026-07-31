"""The drink seam (#2852): advance Intoxicated, roll the pass-out, queue the morning.

One function owns the whole drunk arc so every alcohol/drug item is pure
content (an ``INTOXICATE`` consequence effect with a potency): ``imbibe``
applies or advances the staged ``Intoxicated`` condition, and past the
Blackout threshold each further drink rolls the existing stamina check —
failure lands the built ``Unconscious`` condition (wake rolls, deadlines,
bystander rules all inherited) plus ``Hungover`` for the morning after.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from world.conditions.intoxication_content import (
    HUNGOVER_CONDITION_NAME,
    INTOXICATED_CONDITION_NAME,
    PASS_OUT_BASE_DIFFICULTY,
    PASS_OUT_DIFFICULTY_PER_SEVERITY,
    PASS_OUT_SEVERITY_THRESHOLD,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionTemplate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImbibeResult:
    """Outcome of one drink."""

    applied: bool
    severity: int
    passed_out: bool
    description: str


def imbibe(
    character: ObjectDB,
    *,
    potency: int,
    condition_template: ConditionTemplate | None = None,
) -> ImbibeResult:
    """One dose of *potency* for *character* (#2852; substances #2862).

    ``condition_template`` selects which staged intoxicant ladder advances —
    None keeps alcohol's ``Intoxicated``. The pass-out roll fires only when
    the ladder actually reaches the pass-out threshold (Dusted does; Hazed
    tops out at Blissed and can never drop anyone).
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
        get_active_conditions,
    )

    if potency <= 0:
        return ImbibeResult(False, 0, False, "The drink has no bite at all.")
    template = condition_template
    if template is None:
        template = ConditionTemplate.objects.filter(name=INTOXICATED_CONDITION_NAME).first()
    if template is None:
        logger.warning("Intoxicant template missing; dose had no effect.")
        return ImbibeResult(False, 0, False, "The drink has no effect.")
    active = None
    for instance in get_active_conditions(character):
        if instance.condition_id == template.pk:
            active = instance
            break
    if active is None:
        active = apply_condition(character, template, severity=potency)
        severity = potency
    else:
        advance_condition_severity(active, potency)
        active.refresh_from_db()
        severity = active.severity
    passed_out = False
    if (
        severity >= PASS_OUT_SEVERITY_THRESHOLD
        and _ladder_reaches_pass_out(template)
        and not _stomach_holds(character, severity)
    ):
        passed_out = True
        _pass_out(character)
    description = (
        "The world folds up and puts itself away."
        if passed_out
        else f"The drink lands (severity {severity})."
    )
    return ImbibeResult(True, severity, passed_out, description)


def _ladder_reaches_pass_out(template: ConditionTemplate) -> bool:
    """Whether this intoxicant's staged ladder climbs to the pass-out depth."""
    return template.stages.filter(severity_threshold__gte=PASS_OUT_SEVERITY_THRESHOLD).exists()


def _stomach_holds(character: ObjectDB, severity: int) -> bool:
    """The stamina pass-out roll. Fail-open when the check isn't provisioned."""
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.fatigue.services import _ensure_endurance_check_type  # noqa: PLC0415

    check_type = _ensure_endurance_check_type(ActionCategory.PHYSICAL)
    if check_type is None:
        logger.warning("Stamina endurance check unavailable; the drinker stays up.")
        return True
    difficulty = PASS_OUT_BASE_DIFFICULTY + severity * PASS_OUT_DIFFICULTY_PER_SEVERITY
    result = perform_check(character, check_type, difficulty)
    return result.success_level > 0


def _pass_out(character: ObjectDB) -> None:
    """Drop the drinker: the built Unconscious machinery + Hungover queued."""
    from world.conditions.constants import UNCONSCIOUS_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    for name in (UNCONSCIOUS_CONDITION_NAME, HUNGOVER_CONDITION_NAME):
        template = ConditionTemplate.objects.filter(name=name).first()
        if template is None:
            logger.warning("%s template missing; pass-out incomplete.", name)
            continue
        apply_condition(character, template, severity=1, source_character=character)
    character.msg("|rThe last drink wins. The floor rises up to meet you.|n")
    location = character.location
    if location is not None:
        location.msg_contents(
            f"{character.key} sways once, twice — and folds to the floor, dead drunk.",
            exclude=[character],
        )
