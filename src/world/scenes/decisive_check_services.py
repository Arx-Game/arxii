"""Services for the scene decisive-check marker (#1748).

The decisive-check marker is a GM-declared pre-declaration: "the next graded
check in this scene resolves beat X." When that check resolves, its
CheckOutcome propagates to record_outcome_tier_completion — the same seam
combat and missions use.

Marker creation also activates stakes contracts on the scene's staked beats
(the freeform-scene equivalent of encounter creation), since freeform scenes
have no encounter-start/mission-issue seam.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.scenes.constants import DecisiveCheckMarkerStatus
from world.scenes.models import DecisiveCheckMarker

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona, Scene
    from world.stories.models import Beat
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)


class DecisiveCheckError(ValueError):
    """User-facing error for decisive-check operations."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def get_pending_marker(scene: Scene) -> DecisiveCheckMarker | None:
    """Return the PENDING decisive-check marker on ``scene``, or None."""
    return DecisiveCheckMarker.objects.filter(
        scene=scene,
        status=DecisiveCheckMarkerStatus.PENDING,
    ).first()


def _beat_is_linked_to_scene(beat: Beat, scene: Scene) -> bool:
    """True when the beat's episode is linked to the scene via EpisodeScene."""
    from world.stories.models import EpisodeScene  # noqa: PLC0415

    return EpisodeScene.objects.filter(
        episode_id=beat.episode_id,
        scene=scene,
    ).exists()


def _participant_sheets_for_scene(scene: Scene) -> list[CharacterSheet]:
    """Derive CharacterSheet list from the scene's active participant personas."""
    return [
        persona.character_sheet
        for persona in scene.persona_handler.active_participant_personas()
        if persona.character_sheet_id is not None
    ]


def create_decisive_check_marker(
    *,
    scene: Scene,
    beat: Beat,
    created_by: AccountDB | None = None,
) -> DecisiveCheckMarker:
    """Create a PENDING decisive-check marker and activate stakes.

    Validates:
    - beat.predicate_type == OUTCOME_TIER (record_outcome_tier_completion
      requires this; a GM_MARKED beat lacks the tier-graded resolution path)
    - beat is linked to the scene (via EpisodeScene -> Episode -> Beat)
    - beat.outcome == UNSATISFIED (can't resolve an already-resolved beat)
    - no other PENDING marker on this scene

    On success:
    1. Creates the DecisiveCheckMarker (PENDING)
    2. Calls activate_stakes_for_scene(scene, participant_sheets) — the same
       function combat uses — to lock any staked beats' contracts

    Args:
        scene: The active scene where the decisive check will occur.
        beat: The OUTCOME_TIER beat this check resolves. Must be linked to
            the scene via EpisodeScene and still UNSATISFIED.
        created_by: The GM account creating the marker (audit).

    Returns:
        The newly created PENDING DecisiveCheckMarker.

    Raises:
        DecisiveCheckError: on any validation failure.
    """
    from world.combat.beat_wiring import activate_stakes_for_scene  # noqa: PLC0415
    from world.stories.constants import BeatOutcome, BeatPredicateType  # noqa: PLC0415

    if beat.predicate_type != BeatPredicateType.OUTCOME_TIER:
        msg = (
            f"Beat {beat.pk} is not OUTCOME_TIER (type={beat.predicate_type}). "
            "Only OUTCOME_TIER beats can be resolved by a decisive check."
        )
        raise DecisiveCheckError(msg)

    if not _beat_is_linked_to_scene(beat, scene):
        msg = (
            f"Beat {beat.pk} is not linked to this scene. The beat's episode "
            "must be connected to the scene via an EpisodeScene entry."
        )
        raise DecisiveCheckError(msg)

    if beat.outcome != BeatOutcome.UNSATISFIED:
        msg = (
            f"Beat {beat.pk} is already resolved (outcome={beat.outcome}). "
            "Only unsatisfied beats can be marked as decisive."
        )
        raise DecisiveCheckError(msg)

    if get_pending_marker(scene) is not None:
        msg = (
            "This scene already has a pending decisive-check marker. "
            "Cancel it first with 'scene decisive cancel'."
        )
        raise DecisiveCheckError(msg)

    with transaction.atomic():
        marker = DecisiveCheckMarker.objects.create(
            scene=scene,
            beat=beat,
            created_by=created_by,
            status=DecisiveCheckMarkerStatus.PENDING,
        )
        # Activate stakes for ALL staked beats on the scene's episodes —
        # the same function combat calls at encounter creation. This locks
        # contracts and computes effective risk before the check resolves.
        participant_sheets = _participant_sheets_for_scene(scene)
        if participant_sheets:
            activate_stakes_for_scene(scene, participant_sheets)

    return marker


def cancel_decisive_check_marker(*, marker: DecisiveCheckMarker) -> None:
    """Cancel a PENDING decisive-check marker.

    RESOLVED markers cannot be cancelled (the beat already completed).

    Args:
        marker: The marker to cancel. Must be PENDING.

    Raises:
        DecisiveCheckError: if the marker is not PENDING.
    """
    if marker.status != DecisiveCheckMarkerStatus.PENDING:
        msg = (
            f"Marker {marker.pk} is {marker.status}, not PENDING. "
            "Only pending markers can be cancelled."
        )
        raise DecisiveCheckError(msg)

    marker.status = DecisiveCheckMarkerStatus.CANCELLED
    marker.save(update_fields=["status"])


def maybe_fire_decisive_check(
    *,
    scene: Scene,
    check_outcome: CheckOutcome | None,
    initiator_sheet: CharacterSheet,  # noqa: ARG001 (future: initiator-scoped markers)
    target_persona: Persona | None = None,  # noqa: ARG001 (future: initiator-scoped markers)
) -> DecisiveCheckMarker | None:
    """Hook: after a social check resolves, fire any pending decisive marker.

    Called from all three resolution paths (consent social action, direct
    social action, benign standalone cast). If no PENDING marker exists on
    the scene, no-op. If check_outcome is None (no outcome produced — e.g.
    a paused GATED pipeline or a hostile cast that seeded combat), no-op —
    the marker stays PENDING for the next check.

    ``target_persona`` is carried for future initiator-scoped markers (deferred
    follow-up); it is not used in the MVP "any graded check wins" path.

    On fire:
    1. Derives progress via get_active_progress_for_story(
         marker.beat.episode.chapter.story). If progress is None, no-op
         (the story hasn't been started — log a warning and leave the
         marker PENDING).
    2. Resolves the beat via record_outcome_tier_completion(
         progress=progress, beat=marker.beat, outcome_tier=check_outcome)
    3. Marks the marker RESOLVED with resolved_outcome_tier=check_outcome
    4. Returns the marker (None if no marker fired or progress was None)
    """
    from world.stories.services.beats import record_outcome_tier_completion  # noqa: PLC0415
    from world.stories.services.progress import (  # noqa: PLC0415
        get_active_progress_for_story,
    )

    if check_outcome is None:
        return None

    marker = get_pending_marker(scene)
    if marker is None:
        return None

    beat = marker.beat
    progress = get_active_progress_for_story(beat.episode.chapter.story)
    if progress is None:
        logger.warning(
            "DecisiveCheckMarker %s: beat %s has no active story progress; leaving marker PENDING.",
            marker.pk,
            beat.pk,
        )
        return None

    record_outcome_tier_completion(
        progress=progress,
        beat=beat,
        outcome_tier=check_outcome,
    )

    marker.status = DecisiveCheckMarkerStatus.RESOLVED
    marker.resolved_outcome_tier = check_outcome
    marker.resolved_at = timezone.now()
    marker.save(update_fields=["status", "resolved_outcome_tier", "resolved_at"])

    return marker
