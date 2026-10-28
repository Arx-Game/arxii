"""Emotional conditions feed intensity each round (#4739, slice 3 of #4727).

A ``ConditionStage`` with ``intensity_per_round`` above 0 (an emotional condition such as
Anger, at that stage) adds that much intensity to its bearer's combat engagement at the
start of every round, through the one surge seam (``apply_dramatic_surge``). A player
character with several feeding conditions gets one surge per round for their sum; nothing
is written for a sum of 0. NPC opponents never surge.

Which conditions feed is read from the stage field, never from a name, so renaming a
template changes nothing. Emotional conditions come only from a success or a choice: a
surge band on a failed roll may not carry one (``surge_bands.validate_surge_bands``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import ParticipantStatus, SurgeTriggerKind

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter
    from world.combat.types import DramaticSurgeBeat


def condition_feeds_intensity(condition_ids: Iterable[int]) -> set[int]:
    """The ids among ``condition_ids`` whose template has a stage that feeds intensity.

    One query. A condition feeds when any of its stages has ``intensity_per_round > 0``.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415

    ids = {condition_id for condition_id in condition_ids if condition_id is not None}
    if not ids:
        return set()
    return set(
        ConditionStage.objects.filter(condition_id__in=ids, intensity_per_round__gt=0).values_list(
            "condition_id", flat=True
        )
    )


def condition_intensity_by_target(
    character_ids: Iterable[int],
) -> dict[int, tuple[int, list[str]]]:
    """Per character id: the intensity their conditions feed this round, and their names.

    One query over every character's active, unsuppressed, unresolved condition instances
    whose current stage feeds intensity. The total is the plain sum of each instance's
    ``current_stage.intensity_per_round`` (no stack or severity multiplier). A character
    with nothing feeding is absent from the result. Names are sorted for a stable line.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.conditions.services import _not_suppressed_q  # noqa: PLC0415

    ids = set(character_ids)
    if not ids:
        return {}
    instances = (
        ConditionInstance.objects.filter(
            _not_suppressed_q(),
            target_id__in=ids,
            resolved_at__isnull=True,
            current_stage__intensity_per_round__gt=0,
        )
        .select_related("condition", "current_stage")
        .order_by("target_id", "condition__name")
    )
    fed: dict[int, tuple[int, list[str]]] = {}
    for instance in instances:
        total, names = fed.get(instance.target_id, (0, []))
        names.append(instance.condition.name)
        fed[instance.target_id] = (total + instance.current_stage.intensity_per_round, names)
    return fed


def condition_fed_line(names: list[str], total: int) -> str:
    """The line a condition-fed surge reads as: "<names> · Intensity +<total>".

    The one builder for both clients: telnet sends it to the surged player, and it is stored
    as the record's ``cause``, which the round payload gives the surged player's owner, GMs
    and staff (web parity, #4739).
    """
    return f"{', '.join(names)} · Intensity +{total}"


def apply_condition_intensity_surges(encounter: CombatEncounter) -> list[DramaticSurgeBeat]:
    """Surge every ACTIVE player character whose conditions feed intensity this round.

    Runs at round start (after the escalation tick) and only in an encounter with an
    escalation curve. One ``CONDITION_FED`` record per participant per round
    (``repeat_round`` is the round), so a second call in the same round adds nothing. The
    surge is not announced to the room; the player is told
    "<names> · Intensity +<total>" once the round-opening commits, and the web reads the
    same line as the record's ``cause`` through the round payload.
    """
    from world.combat.escalation import apply_dramatic_surge  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    if encounter.escalation_curve is None:
        return []
    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    if not participants:
        return []
    fed = condition_intensity_by_target(
        participant.character_sheet.character_id for participant in participants
    )
    fed_participants = [
        participant
        for participant in participants
        if fed.get(participant.character_sheet.character_id, (0, []))[0] > 0
    ]
    if not fed_participants:
        return []
    beats: list[DramaticSurgeBeat] = []
    for participant in fed_participants:
        character = participant.character_sheet.character
        total, names = fed[character.pk]
        line = condition_fed_line(names, total)
        beat = apply_dramatic_surge(
            encounter=encounter,
            participant=participant,
            amount=total,
            trigger_kind=SurgeTriggerKind.CONDITION_FED,
            repeat_round=encounter.round_number,
            narrate=False,
            cause=line,
        )
        if beat is None:
            continue
        beats.append(beat)
        transaction.on_commit(lambda character=character, line=line: character.msg(line))
    return beats
