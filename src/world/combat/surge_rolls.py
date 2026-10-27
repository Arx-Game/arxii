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
from world.combat.models import DramaticSurgeRecord, SurgeDegreeBand, SurgeTuning
from world.mechanics.constants import EngagementType

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    SurgeTriggerKind.ALLY_HURT: "bond difficulty",
}


def persona_name_of(participant: CombatParticipant) -> str:
    """The name other characters know ``participant`` by (never ``str(participant)``).

    The persona name, falling back to the character's key when the sheet has no persona.
    """
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    sheet_id = participant.character_sheet_id
    names = persona_names_for_sheets([sheet_id])
    return names.get(sheet_id, participant.character_sheet.character.key)


def rolled_surge_possible(
    encounter: CombatEncounter,
    participant: CombatParticipant,
    trigger_kind: str,
    subject_sheet: CharacterSheet | None,
) -> bool:
    """Whether a rolled surge for this beat could still be written this round (#4737).

    True when the participant has a COMBAT engagement sourced to ``encounter`` and no
    rolled record exists yet for (encounter, participant, kind, this round, subject): the
    two things ``apply_dramatic_surge`` checks before it writes. A caller asks this before
    rolling, so a roll that could only be swallowed never spends a contributing condition
    or prints a line. It must mirror ``apply_dramatic_surge``'s dedup key, and
    ``escalation._hurt_ally_rollers`` mirrors it in batch form.
    """
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    from world.combat.models import CombatEncounter as _CombatEncounter  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    engaged = CharacterEngagement.objects.filter(
        character=participant.character_sheet,
        engagement_type=EngagementType.COMBAT,
        source_content_type=ContentType.objects.get_for_model(_CombatEncounter),
        source_id=encounter.pk,
    ).exists()
    if not engaged:
        return False
    return not DramaticSurgeRecord.objects.filter(
        encounter=encounter,
        participant=participant,
        trigger_kind=trigger_kind,
        repeat_round=encounter.round_number,
        subject_sheet=subject_sheet,
    ).exists()


def surge_tuning_for(trigger_kind: str, *, warn: bool = True) -> SurgeTuning | None:
    """The ``SurgeTuning`` authored for ``trigger_kind``, or None with a logged warning.

    ``warn=False`` stays quiet for a caller on a per-hit path (the hurt-ally surge), where a
    row staff have not authored yet is not an event worth a log line every hit.

    Always looked up by kind, never by name. Callers that roll before they surge (an NPC
    taunt) read it first so a missing row skips the roll as well as the surge.
    """
    tuning = (
        SurgeTuning.objects.select_related("check_type").filter(trigger_kind=trigger_kind).first()
    )
    if tuning is None and warn:
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
    # Imported here: the services package imports this module (rally, taunt), so a module
    # level import made importing surge_rolls first a circular import.
    from world.combat.services.declarations.social_check import (  # noqa: PLC0415
        roll_social_check,
    )

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
    return pick_band(list(tuning.bands.select_related("outcome", "condition")), outcome)


def pick_band(
    bands: Sequence[SurgeDegreeBand],
    outcome: CheckOutcome,
) -> SurgeDegreeBand | None:
    """The band in ``bands`` for ``outcome``, or the nearest worse one (#4737).

    ``bands`` must carry their ``outcome`` loaded. The pure half of ``band_for_outcome``,
    so a reader holding a tuning's prefetched bands (the round payload) picks without a
    query per record.
    """
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


def roll_line(  # noqa: PLR0913 - the line is built from each part of the roll
    *,
    check_type: CheckType,
    trigger_kind: str,
    potency: int | None,
    outcome: CheckOutcome,
    amount: int,
    control_change: int,
    condition_name: str,
) -> str:
    """The caption the surged player sees, for example
    ``Composure check vs taunt potency 60 · Failure · Intensity +2 · control -1 · Goaded``.

    Parts are joined with " · ". Control appears only when it changed, the condition name
    last and only when it applied, and a hurt ally's intensity says it was scaled by the
    wound. The surged player's character is sent it live; the round payload rebuilds it
    from the stored record for the same viewers (#4737).
    """
    label = POTENCY_LABELS.get(trigger_kind, "difficulty")
    against = f" vs {label} {potency}" if potency is not None else ""
    intensity = f"Intensity +{amount}"
    if trigger_kind == SurgeTriggerKind.ALLY_HURT:
        intensity += " (scaled by the wound)"
    parts = [f"{check_type.name} check{against}", outcome.name, intensity]
    if control_change:
        parts.append(f"control {control_change:+d}")
    if condition_name:
        parts.append(condition_name)
    return " · ".join(parts)


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
    tuning: SurgeTuning | None = None,
    cause: str = "",
) -> DramaticSurgeBeat | None:
    """Write one rolled surge from the band the roll's outcome picks (#4737).

    A quiet no-op (None) when the encounter has no escalation curve (ADR-0098), when no
    ``SurgeTuning`` is authored for ``trigger_kind`` (logged), when no band fits the
    outcome, or when the scaled amount is 0 and the band carries neither a control change
    nor a condition (nothing to write, so the round's dedup slot stays free). A band that
    scales to 0 intensity but still changes control or applies a condition is written, with
    no "power surges" room line. Otherwise the surge is written through
    ``apply_dramatic_surge`` with ``repeat_round`` set to the encounter's round: a later
    round surges again, the same round and subject surges once. ``intensity_scale`` scales
    the band's intensity (a hurt ally's depth, say). A band's condition is applied to the
    participant's character when the surge was written, with ``source_character`` as its
    source; the roll line and the beat name it only if it actually applied. The surge and
    the condition are written in one transaction.

    A caller that already read the ``SurgeTuning`` passes it as ``tuning`` so it is not
    looked up again for each participant; omitted, it is looked up by ``trigger_kind``.

    ``cause`` is the line the surged player, GMs and staff read for this surge (who taunted
    or rallied, or the wound); it is stored on the record and never shown to others.

    The roll line goes to the surged player's character only, once the surrounding
    transaction commits; the room still gets just the generic narration
    ``apply_dramatic_surge`` sends.
    """
    if encounter.escalation_curve is None:
        return None
    if tuning is None:
        tuning = surge_tuning_for(trigger_kind)
    if tuning is None:
        return None
    band = band_for_outcome(tuning, outcome)
    if band is None or outcome is None:
        logger.warning("SurgeTuning %s has no band for the roll outcome; no surge.", trigger_kind)
        return None

    # Half-up, not round(): banker's rounding turns an intensity-1 band at half scale to 0.
    amount = math.floor(band.intensity * intensity_scale + 0.5)
    if amount == 0 and not band.control_change and band.condition is None:
        return None
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
            narrate=amount > 0,
            cause=cause,
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
                record = DramaticSurgeRecord.objects.get(pk=beat.record_id)
                record.condition = band.condition
                record.save(update_fields=["condition"])
    line = roll_line(
        check_type=tuning.check_type,
        trigger_kind=trigger_kind,
        potency=potency,
        outcome=outcome,
        amount=amount,
        control_change=band.control_change,
        condition_name=condition_name,
    )
    # The round resolves inside an atomic block: tell the player once it has committed.
    transaction.on_commit(lambda: character.msg(line))
    return replace(beat, condition_name=condition_name)
