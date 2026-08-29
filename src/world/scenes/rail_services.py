"""GM story rail (#3434) — a composed, per-viewer read of a scene's running-beat
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
    (``HasGMTrust`` — the DRF counterpart to ``MinimumGMLevelPrerequisite``,
    the same bar ``GMListConditionsAction`` gates on). Deliberately narrower
    than ``IsSceneGMOrOwnerOrStaff``: a scene *owner* who isn't also its GM
    gets nothing from this endpoint — see the anti-reinvention ledger in
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

    Mirrors ``world.scenes.round_services._present_character_sheets`` — kept
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


def _viewer_has_story_standing(user: AccountDB, story: Any) -> bool:
    """Staff, or the SAME scoping ``IsProtectedSubjectStoryOwnerOrStaff`` uses.

    CRITICAL leak invariant (#3434 spec): must never be looser than
    ``user_owns_or_leads_story`` — a scene co-GM with no standing on the
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

    id/kind/risk/outcome/predicate state/pools-authored booleans only — never
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
    }


def build_gm_story_rail_payload(scene: Scene, user: AccountDB) -> dict[str, Any]:
    """Compose the GM story rail payload for ``user`` viewing ``scene``.

    Caller (the view) has already confirmed ``viewer_qualifies_for_rail`` —
    this function computes the finer-grained per-section gating on top:
    story-privileged content (internal_description, opponent/staged lines,
    protected subjects) and staff-only clue placements.
    """
    from world.stories.serializers import (  # noqa: PLC0415
        BeatOpponentLineSerializer,
        BeatStagedTemplateSerializer,
        StoryProtectedSubjectSerializer,
    )

    beat = scene.running_beat
    beat_payload: dict[str, Any] | None = None
    protected_subjects: Any = []

    if beat is not None:
        beat_payload = _serialize_beat_summary(beat)
        story = beat.episode.chapter.story
        if _viewer_has_story_standing(user, story):
            beat_payload["internal_description"] = beat.internal_description
            beat_payload["opponent_lines"] = BeatOpponentLineSerializer(
                beat.opponent_lines.all(), many=True
            ).data
            beat_payload["staged_templates"] = BeatStagedTemplateSerializer(
                beat.staged_templates.all(), many=True
            ).data
            protected_subjects = StoryProtectedSubjectSerializer(
                story.protected_subjects.filter(is_active=True), many=True
            ).data

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
        "clue_placements": clue_placements,
        "participants": participants,
    }
