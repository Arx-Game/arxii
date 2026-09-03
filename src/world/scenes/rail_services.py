"""GM story rail (#3434) - a composed, per-viewer read of a scene's running-beat
authored material plus participant conditions/vitals seams.

No new models, no writes: this is a read-only aggregation over Beat/
StoryProtectedSubject/RoomClue/room-contents, gated per section to the exact
scoping the source data already enforces elsewhere (never a looser copy).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.scenes.models import Scene


def viewer_qualifies_for_rail(request: Any, view: Any, scene: Scene) -> bool:
    """Whether the requesting user may see the GM story rail for ``scene`` at all.

    Staff bypass, else ``scene.is_gm(user)`` AND at least JUNIOR GM trust
    (``HasGMTrust`` - the DRF counterpart to ``MinimumGMLevelPrerequisite``,
    the same bar ``GMListConditionsAction`` gates on). Deliberately narrower
    than ``IsSceneGMOrOwnerOrStaff``: a scene *owner* who isn't also its GM
    gets nothing from this endpoint - see the anti-reinvention ledger in
    #3434's spec.
    """
    from world.gm.permissions import HasGMTrust  # noqa: PLC0415

    user = request.user
    if user.is_staff:
        return True
    if not scene.is_gm(user):
        return False
    return HasGMTrust().has_permission(request, view)


def _present_character_sheets(location: Any) -> list[Any]:
    """CharacterSheets of characters currently in ``location`` (walks room.contents).

    Mirrors ``world.scenes.round_services._present_character_sheets`` - kept
    local (not imported) since that helper is private to its module.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    present = []
    for obj in location.contents:
        try:
            sheet = obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        present.append(sheet)
    return present


def viewer_has_story_standing(user: AccountDB, story: Any) -> bool:
    """Staff, or the SAME scoping ``IsProtectedSubjectStoryOwnerOrStaff`` uses.

    CRITICAL leak invariant (#3434 spec): must never be looser than
    ``user_owns_or_leads_story`` - a scene co-GM with no standing on the
    running story must get an empty protected-subjects section and no
    ``internal_description``/line details, matching
    ``stories/permissions.py:1624``'s "never readable by non-owner/
    non-lead-GM" contract verbatim.
    """
    from world.stories.permissions import user_owns_or_leads_story  # noqa: PLC0415

    if user.is_staff:
        return True
    return user_owns_or_leads_story(user, story)


def _serialize_beat_summary(beat: Any) -> dict[str, Any]:
    """The low-sensitivity refereeing metadata any qualifying scene GM sees.

    id/kind/risk/outcome/predicate state/pools-authored booleans only - never
    internal_description or line details (those are gated separately by
    story standing, see ``build_gm_story_rail_payload``).
    """
    return {
        "id": beat.id,
        "kind": beat.kind,
        "risk": beat.risk,
        "outcome": beat.outcome,
        "predicate_type": beat.predicate_type,
        "success_consequences_authored": beat.success_consequences_id is not None,
        "failure_consequences_authored": beat.failure_consequences_id is not None,
        "expired_consequences_authored": beat.expired_consequences_id is not None,
        "internal_description": None,
        "opponent_lines": None,
        "staged_templates": None,
        "staged_battle": None,
    }


def _serialize_stakes(beat: Any) -> list[dict[str, Any]]:
    """The beat's stakes contract, per-stake, with its fired outcome if any (#3561).

    ``StakeOutcome`` carries a unique constraint on ``stake`` - at most one row
    per stake - so ``prefetched_outcomes[0]`` is the fired outcome
    deterministically; a stake with no ``StakeOutcome`` yet (unresolved) gets
    ``outcome: None``. ``resolution`` is nullable on ``StakeOutcome`` (no branch
    was authored for the fired column), so ``outcome_key``/``resolution_summary``
    fall back to blank in that case, never a crash.
    """
    from django.db.models import Prefetch  # noqa: PLC0415

    from world.stories.models import StakeOutcome  # noqa: PLC0415

    stakes = list(
        beat.stakes.prefetch_related(
            Prefetch(
                "outcomes",
                queryset=StakeOutcome.objects.select_related("resolution"),
                to_attr="prefetched_outcomes",
            )
        )
    )
    payload: list[dict[str, Any]] = []
    for stake in stakes:
        outcome = stake.prefetched_outcomes[0] if stake.prefetched_outcomes else None
        outcome_payload: dict[str, Any] | None = None
        if outcome is not None:
            resolution = outcome.resolution
            outcome_payload = {
                "column": outcome.column,
                "outcome_key": resolution.outcome_key if resolution is not None else "",
                "resolution_summary": (
                    resolution.narrative_summary if resolution is not None else ""
                ),
            }
        payload.append(
            {
                "id": stake.pk,
                "player_summary": stake.player_summary,
                "severity": stake.severity,
                "subject_kind": stake.subject_kind,
                "outcome": outcome_payload,
            }
        )
    return payload


def _serialize_activation(beat: Any) -> dict[str, Any] | None:
    """The beat's locked contract state, if it has ever been activated (#3561).

    Prefers the open (unresolved) activation; when none is open, falls back to
    the most recent one so a resolved contract still shows its lock instead of
    silently disappearing from the rail. ``None`` only when the beat has never
    been activated.
    """
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    activation = get_open_activation(beat) or beat.stake_activations.order_by("-locked_at").first()
    if activation is None:
        return None
    return {
        "locked_at": activation.locked_at,
        "effective_risk": activation.effective_risk,
        "is_ready": activation.is_ready,
    }


def build_gm_story_rail_payload(scene: Scene, user: AccountDB) -> dict[str, Any]:
    """Compose the GM story rail payload for ``user`` viewing ``scene``.

    Caller (the view) has already confirmed ``viewer_qualifies_for_rail`` -
    this function computes the finer-grained per-section gating on top:
    story-privileged content (internal_description, opponent/staged lines,
    protected subjects) and staff-only clue placements.
    """
    from world.stories.models import BeatStagedBattle  # noqa: PLC0415
    from world.stories.serializers import (  # noqa: PLC0415
        BeatOpponentLineSerializer,
        BeatStagedTemplateSerializer,
        StoryProtectedSubjectSerializer,
    )

    beat = scene.running_beat
    beat_payload: dict[str, Any] | None = None
    protected_subjects: Any = []
    stakes: Any = []
    activation: Any = None

    if beat is not None:
        beat_payload = _serialize_beat_summary(beat)
        story = beat.episode.chapter.story
        if viewer_has_story_standing(user, story):
            beat_payload["internal_description"] = beat.internal_description
            beat_payload["opponent_lines"] = BeatOpponentLineSerializer(
                beat.opponent_lines.all(), many=True
            ).data
            beat_payload["staged_templates"] = BeatStagedTemplateSerializer(
                beat.staged_templates.all(), many=True
            ).data
            staged = BeatStagedBattle.objects.filter(beat=beat).select_related("blueprint").first()
            if staged is not None:
                beat_payload["staged_battle"] = {
                    "blueprint_name": staged.blueprint.name,
                    "name": staged.name,
                    "party_side_role": staged.party_side_role,
                    "unit_line_count": staged.unit_lines.count(),
                }
            protected_subjects = StoryProtectedSubjectSerializer(
                story.protected_subjects.filter(is_active=True), many=True
            ).data
            stakes = _serialize_stakes(beat)
            activation = _serialize_activation(beat)

    clue_placements: list[dict[str, Any]] = []
    if user.is_staff and scene.location_id is not None:
        from world.clues.models import RoomClue  # noqa: PLC0415

        clue_placements = [
            {
                "id": room_clue.id,
                "clue_name": room_clue.clue.name,
                "detect_difficulty": room_clue.detect_difficulty,
                "is_active": room_clue.is_active,
            }
            for room_clue in RoomClue.objects.filter(
                room_profile_id=scene.location_id, is_active=True
            ).select_related("clue")
        ]

    participants: list[dict[str, Any]] = []
    if scene.location_id is not None:
        participants.extend(
            {"character_sheet_id": sheet.pk, "name": sheet.character.db_key}
            for sheet in _present_character_sheets(scene.location)
        )

    return {
        "beat": beat_payload,
        "protected_subjects": protected_subjects,
        "stakes": stakes,
        "activation": activation,
        "clue_placements": clue_placements,
        "participants": participants,
    }
