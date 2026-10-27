"""Rolled dramatic surges (#4737): a roll with degrees picks how hard a beat hits.

A taunt, a rally and a hurt bonded ally each raise a player character's combat
engagement through a roll. Staff author one ``SurgeTuning`` per trigger kind (which check,
what potency) with ``SurgeDegreeBand`` rows per check outcome (intensity, control change,
an optional condition). This module rolls the check, picks the band for the outcome and
writes the surge through ``apply_dramatic_surge``, the one seam every surge uses.

Player characters roll; a non-player opponent only supplies a potency number.
"""

from __future__ import annotations

from dataclasses import replace
import logging
import math
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import SurgeTriggerKind
from world.combat.escalation import apply_dramatic_surge
from world.combat.models import SurgeDegreeBand, SurgeTuning
from world.combat.services.declarations.social_check import roll_social_check

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.combat.models import CombatEncounter, CombatParticipant
    from world.combat.types import DramaticSurgeBeat
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)

# What the roll line calls the number the roll was made against, per trigger kind.
POTENCY_LABELS: dict[str, str] = {
    SurgeTriggerKind.TAUNT_RECEIVED: "taunt potency",
    SurgeTriggerKind.RALLIED: "rally difficulty",
    SurgeTriggerKind.ALLY_HURT: "peril difficulty",
}


def surge_tuning_for(trigger_kind: str) -> SurgeTuning | None:
    """The ``SurgeTuning`` authored for ``trigger_kind``, or None with a logged warning.

    Always looked up by kind, never by name. Callers that roll before they surge (an NPC
    taunt) read it first so a missing row skips the roll as well as the surge.
    """
    tuning = (
        SurgeTuning.objects.select_related("check_type").filter(trigger_kind=trigger_kind).first()
    )
    if tuning is None:
        logger.warning("No SurgeTuning is authored for trigger kind %s; no surge.", trigger_kind)
    return tuning


def surge_roll_for_participant(
    participant: CombatParticipant,
    check_type: CheckType,
    potency: int,
) -> CheckResult:
    """Roll ``check_type`` for the participant's character against ``potency`` (#4737).

    The same modifier handling as the social combat verbs (``roll_social_check``), so a
    surge roll gets the situational perks and spends contributing conditions exactly as a
    Rally or Taunt roll does.
    """
    return roll_social_check(participant, check_type, potency)


def band_for_outcome(
    tuning: SurgeTuning,
    outcome: CheckOutcome | None,
) -> SurgeDegreeBand | None:
    """The band authored for ``outcome``, falling back to the nearest worse one (#4737).

    With no band for the outcome itself, the band with the greatest ``success_level`` not
    above the outcome's; with none that low, the lowest band. None when the tuning has no
    bands or there is no outcome (the check could not run).
    """
    if outcome is None:
        return None
    bands = list(tuning.bands.select_related("outcome", "condition"))
    if not bands:
        return None
    for band in bands:
        if band.outcome_id == outcome.pk:
            return band
    level = outcome.success_level
    at_or_below = [band for band in bands if band.outcome.success_level <= level]
    if at_or_below:
        return max(at_or_below, key=lambda band: band.outcome.success_level)
    return min(bands, key=lambda band: band.outcome.success_level)


def _roll_line(  # noqa: PLR0913 - the line is built from each part of the roll
    *,
    check_type: CheckType,
    trigger_kind: str,
    potency: int | None,
    outcome: CheckOutcome,
    amount: int,
    control_change: int,
    condition_name: str,
) -> str:
    """The system line the surged player sees, for example
    ``Composure check vs taunt potency 14. Partial. Intensity +5, control 0.``"""
    against = f" vs {POTENCY_LABELS[trigger_kind]} {potency}" if potency is not None else ""
    control = f"{control_change:+d}" if control_change else "0"
    line = (
        f"{check_type.name} check{against}. {outcome.name}. Intensity +{amount}, control {control}."
    )
    if condition_name:
        line += f" {condition_name}."
    return line


def apply_rolled_surge(  # noqa: PLR0913 - keyword-only surge fields, cohesive
    *,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    trigger_kind: str,
    outcome: CheckOutcome | None,
    potency: int | None,
    subject_sheet: CharacterSheet | None = None,
    intensity_scale: float = 1.0,
    source_character: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM - the taunter, any object
) -> DramaticSurgeBeat | None:
    """Write one rolled surge from the band the roll's outcome picks (#4737).

    A quiet no-op (None) when the encounter has no escalation curve (ADR-0098), when no
    ``SurgeTuning`` is authored for ``trigger_kind`` (logged), or when no band fits the
    outcome. Otherwise the surge is written through ``apply_dramatic_surge`` with
    ``repeat_round`` set to the encounter's round: a later round surges again, the same
    round and subject surges once. ``intensity_scale`` scales the band's intensity (a
    hurt ally's depth, say). A band's condition is applied to the participant's character
    when the surge was written, with ``source_character`` as its source; the roll line and
    the beat name it only if it actually applied. The surge and the condition are written
    in one transaction.

    The roll line goes to the surged player's character only; the room still gets just
    the generic narration ``apply_dramatic_surge`` sends.
    """
    if encounter.escalation_curve is None:
        return None
    tuning = surge_tuning_for(trigger_kind)
    if tuning is None:
        return None
    band = band_for_outcome(tuning, outcome)
    if band is None or outcome is None:
        logger.warning("SurgeTuning %s has no band for the roll outcome; no surge.", trigger_kind)
        return None

    # Half-up, not round(): banker's rounding turns an intensity-1 band at half scale to 0.
    amount = math.floor(band.intensity * intensity_scale + 0.5)
    character = participant.character_sheet.character
    condition_name = ""
    # One transaction: if applying the condition raises, the surge record rolls back too,
    # so a retry is not swallowed by the dedup with the condition lost.
    with transaction.atomic():
        beat = apply_dramatic_surge(
            encounter=encounter,
            participant=participant,
            amount=amount,
            trigger_kind=trigger_kind,
            subject_sheet=subject_sheet,
            outcome=outcome,
            potency=potency,
            control_change=band.control_change,
            repeat_round=encounter.round_number,
        )
        if beat is None:
            return None
        if band.condition is not None:
            from world.conditions.services import apply_condition  # noqa: PLC0415

            applied = apply_condition(
                character,
                band.condition,
                source_character=source_character,
                source_description="Surge roll",
            )
            # A trigger can cancel it, a resist can turn it away, another condition can
            # prevent it; only name it when an instance exists.
            if applied.success and applied.instance is not None:
                condition_name = band.condition.name
    character.msg(
        _roll_line(
            check_type=tuning.check_type,
            trigger_kind=trigger_kind,
            potency=potency,
            outcome=outcome,
            amount=amount,
            control_change=band.control_change,
            condition_name=condition_name,
        )
    )
    return replace(beat, condition_name=condition_name)
