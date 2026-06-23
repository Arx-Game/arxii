"""Lifecycle services for non-combat scene rounds."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


def actions_this_round(scene_round: SceneRound, participant: SceneRoundParticipant) -> int:
    """Return the number of action declarations for a participant in the current round."""
    return scene_round.action_declarations.filter(
        round_number=scene_round.round_number, participant=participant
    ).count()


def distinct_actors_this_round(scene_round: SceneRound) -> int:
    """Return the number of distinct participants with declarations in the current round."""
    return (
        scene_round.action_declarations.filter(round_number=scene_round.round_number)
        .values("participant_id")
        .distinct()
        .count()
    )


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
    """True while any ACTIVE participant still carries a danger-keeping condition.

    A DANGER round persists (keeps ticking) while a participant is Bleeding-Out or
    Plummeting (#1228) — the descent must keep advancing until the fall resolves
    (impact removes the Plummeting condition), then the round auto-ends.
    """
    from world.areas.positioning.constants import PLUMMETING_CONDITION_NAME  # noqa: PLC0415
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
        target_id__in=char_ids,
        condition__name__in=[BLEED_OUT_CONDITION_NAME, PLUMMETING_CONDITION_NAME],
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


def scene_round_is_complete(scene_round: SceneRound) -> bool:
    """Presence-gated completion: True when every ACTIVE participant present in the room
    has a declaration/pass row for the current round. Absent participants are implicit
    passes (never block). No timer — presence is the idle signal (AFK-safety)."""
    present_ids = {s.character_id for s in _present_character_sheets(scene_round.room)}
    active = scene_round.participants.filter(
        status=SceneRoundParticipantStatus.ACTIVE
    ).select_related("character_sheet")
    declared_ids = set(
        scene_round.action_declarations.filter(
            round_number=scene_round.round_number, is_immediate=False
        ).values_list("participant_id", flat=True)
    )
    present_active = [p for p in active if p.character_sheet.character_id in present_ids]
    if not present_active:
        return False  # nobody present to drive resolution
    return all(p.pk in declared_ids for p in present_active)


@transaction.atomic
def resolve_scene_round(scene_round: SceneRound) -> SceneRound:
    """Unconditionally resolve a DECLARING social round: execute declared CHALLENGE actions
    in initiative order, fire the shared END tick, delete the round's bridge rows, then
    advance to the next round (DECLARING).

    Callers gate WHEN to resolve: ``maybe_resolve_scene_round`` resolves only once the
    presence-gated completion rule is met; a GM force-resolve calls this directly to resolve
    an incomplete round (undeclared present participants are swept as implicit passes)."""
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status != RoundStatus.DECLARING:
        msg = f"Cannot resolve scene round: status is {rnd.status}, expected declaring."
        raise ValueError(msg)
    if rnd.start_reason == SceneRoundStartReason.DANGER:
        # Danger rounds are the #1046 acute tier: they tick via advance_scene_round_for_action
        # and auto-end on _danger_persists. They must never be resolved as a social round
        # (that would bypass the danger auto-end). This is the social-only resolver.
        msg = "Cannot resolve a danger round as a social round; it ticks via the acute tier."
        raise ValueError(msg)
    rnd.status = RoundStatus.RESOLVING
    rnd.save(update_fields=["status"])

    _resolve_scene_declarations(rnd)

    targets = [
        p.character_sheet.character
        for p in rnd.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).select_related(
            "character_sheet__character"
        )
    ]
    tick_round_for_targets(targets, timing="end")

    rnd.status = RoundStatus.BETWEEN_ROUNDS
    rnd.save(update_fields=["status"])
    start_scene_round(rnd)  # -> DECLARING, round_number += 1
    scene_round.refresh_from_db()
    return scene_round


def maybe_resolve_scene_round(scene_round: SceneRound) -> SceneRound:
    """Resolve iff the presence-gated completion rule is met. No-op otherwise."""
    if scene_round.status == RoundStatus.DECLARING and scene_round_is_complete(scene_round):
        return resolve_scene_round(scene_round)
    return scene_round


def _resolve_scene_declarations(scene_round: SceneRound) -> None:
    """Resolve declared CHALLENGE actions for the round in initiative order, re-validating
    eligibility via get_available_actions (mirrors combat _resolve_declared_challenges),
    then delete ALL bridge rows for the round. Pass rows resolve to nothing."""
    from world.mechanics.challenge_resolution import resolve_challenge  # noqa: PLC0415
    from world.mechanics.services import get_available_actions  # noqa: PLC0415

    declarations = list(
        scene_round.action_declarations.filter(
            round_number=scene_round.round_number, is_pass=False, is_immediate=False
        )
        .select_related(
            "participant",
            "participant__character_sheet",
            "participant__character_sheet__character",
            "challenge_instance",
            "challenge_instance__location",
            "challenge_approach",
        )
        .order_by("participant__initiative_order", "declared_at", "pk")
    )
    for decl in declarations:
        character = decl.participant.character_sheet.character
        challenge_instance = decl.challenge_instance
        approach = decl.challenge_approach
        location = challenge_instance.location
        available_actions = get_available_actions(character, location)
        matching = next(
            (
                a
                for a in available_actions
                if a.challenge_instance_id == challenge_instance.pk and a.approach_id == approach.pk
            ),
            None,
        )
        if matching is None:
            logger.warning(
                "Skipping deferred scene challenge declaration for participant %s "
                "(challenge_instance=%s, approach=%s): no matching AvailableAction.",
                decl.participant_id,
                challenge_instance.pk,
                approach.pk,
            )
            continue
        outcome = resolve_challenge(
            character, challenge_instance, approach, matching.capability_source
        )
        if outcome is not None and outcome.check_result is not None:
            from world.scenes.interaction_services import (  # noqa: PLC0415
                broadcast_scene_outcome,
                render_challenge_outcome_narration,
            )

            narration = render_challenge_outcome_narration(
                actor_label=character.db_key,
                challenge_name=outcome.challenge_name,
                approach_name=outcome.approach_name,
                outcome_label=outcome.check_result.outcome_name,
                success_level=outcome.check_result.success_level,
            )
            broadcast_scene_outcome(scene_round=scene_round, narration=narration)

    scene_round.action_declarations.filter(round_number=scene_round.round_number).delete()
