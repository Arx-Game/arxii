"""Lifecycle services for non-combat scene rounds."""

from django.db import transaction
from django.utils import timezone

from world.scenes.constants import RoundStatus, SceneRoundParticipantStatus
from world.scenes.models import SceneRound
from world.vitals.services import tick_round_for_targets


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
