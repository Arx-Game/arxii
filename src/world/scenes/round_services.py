"""Lifecycle services for non-combat scene rounds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from world.scenes.constants import (
    ACTIVE_SCENE_ROUND_STATUSES,
    RoundStatus,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.models import SceneRound, SceneRoundParticipant
from world.vitals.services import tick_round_for_targets

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


@transaction.atomic
def start_scene_round(scene_round: SceneRound) -> SceneRound:
    """Advance a BETWEEN_ROUNDS round into DECLARING (round_number += 1)."""
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status != RoundStatus.BETWEEN_ROUNDS:
        msg = f"Cannot start scene round: status is {rnd.status}, expected between_rounds."
        raise ValueError(msg)
    rnd.round_number += 1
    rnd.status = RoundStatus.DECLARING
    rnd.round_started_at = timezone.now()
    rnd.save(update_fields=["round_number", "status", "round_started_at"])
    scene_round.refresh_from_db()
    return scene_round


@transaction.atomic
def advance_scene_round(scene_round: SceneRound) -> SceneRound:
    """Resolve the current round: fire the shared END tick for all ACTIVE
    participants, then return to BETWEEN_ROUNDS.

    Resolving declared actions into outcomes is deferred to the acute-tier plan;
    this foundation drives only the effect tick.
    """
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status != RoundStatus.DECLARING:
        msg = f"Cannot advance scene round: status is {rnd.status}, expected declaring."
        raise ValueError(msg)
    rnd.status = RoundStatus.RESOLVING
    rnd.save(update_fields=["status"])

    targets = [
        p.character_sheet.character
        for p in rnd.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).select_related(
            "character_sheet__character"
        )
    ]
    tick_round_for_targets(targets, timing="end")

    rnd.status = RoundStatus.BETWEEN_ROUNDS
    rnd.save(update_fields=["status"])
    scene_round.refresh_from_db()
    return scene_round


@transaction.atomic
def end_scene_round(scene_round: SceneRound) -> SceneRound:
    """Mark a scene round COMPLETED."""
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    rnd.status = RoundStatus.COMPLETED
    rnd.completed_at = timezone.now()
    rnd.save(update_fields=["status", "completed_at"])
    scene_round.refresh_from_db()
    return scene_round


@transaction.atomic
def advance_scene_round_for_action(scene_round: SceneRound) -> SceneRound:
    """Drive one tick of a scene round in response to a participant's action.

    Cycles BETWEEN_ROUNDS -> DECLARING -> (tick) -> BETWEEN_ROUNDS, reusing the
    foundation lifecycle services. For a DANGER-started round, auto-ends
    (COMPLETED) once no ACTIVE participant is Bleeding-Out (stabilized/removed/dead).
    """
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status == RoundStatus.BETWEEN_ROUNDS:
        start_scene_round(rnd)
        rnd.refresh_from_db()
    if rnd.status == RoundStatus.DECLARING:
        advance_scene_round(rnd)
        rnd.refresh_from_db()
    if rnd.start_reason == SceneRoundStartReason.DANGER and not _danger_persists(rnd):
        end_scene_round(rnd)
        rnd.refresh_from_db()
    scene_round.refresh_from_db()
    return scene_round


def _danger_persists(scene_round: SceneRound) -> bool:
    """True if any ACTIVE participant still has a Bleeding-Out condition."""
    from world.conditions.constants import BLEED_OUT_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    char_ids = list(
        scene_round.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).values_list(
            "character_sheet__character_id", flat=True
        )
    )
    if not char_ids:
        return False
    return ConditionInstance.objects.filter(
        target_id__in=char_ids, condition__name=BLEED_OUT_CONDITION_NAME
    ).exists()


def _present_character_sheets(room: ObjectDB) -> list[CharacterSheet]:
    """CharacterSheets of characters currently in ``room`` (walks room.contents; no per-object query)."""  # noqa: E501
    present = []
    for obj in room.contents:
        try:
            sheet = obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        present.append(sheet)
    return present


@transaction.atomic
def auto_start_or_extend_danger_round(character_sheet: CharacterSheet) -> SceneRound | None:
    """Ensure a DANGER scene round exists for the character's room and enrol all present
    characters. Returns the round, or None if the character has no room. Caller guarantees
    the character is NOT in active combat. One active round per room (foundation constraint)."""
    room = character_sheet.character.location
    if room is None:
        return None
    rnd = SceneRound.objects.filter(room=room, status__in=ACTIVE_SCENE_ROUND_STATUSES).first()
    if rnd is None:
        rnd = SceneRound.objects.create(room=room, start_reason=SceneRoundStartReason.DANGER)
        start_scene_round(rnd)
        rnd.refresh_from_db()
    for sheet in _present_character_sheets(room):
        SceneRoundParticipant.objects.get_or_create(scene_round=rnd, character_sheet=sheet)
    return rnd
