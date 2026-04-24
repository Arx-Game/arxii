"""Story log query + visibility filtering.

The story log is a chronological stream of BeatCompletion and
EpisodeResolution entries for a story. Visibility filtering applies
HINTED/SECRET/VISIBLE rules based on the requester's viewer role.
"""

from __future__ import annotations

from datetime import datetime

from world.stories.constants import BeatVisibility
from world.stories.models import (
    BeatCompletion,
    EpisodeResolution,
    Story,
)
from world.stories.permissions import (
    VIEWER_ROLE_LEAD_GM,
    VIEWER_ROLE_NO_ACCESS,
    VIEWER_ROLE_PLAYER,
    VIEWER_ROLE_STAFF,
)
from world.stories.types import (
    AnyStoryProgress,
    StoryLogBeatEntry,
    StoryLogEpisodeEntry,
)

_PRIVILEGED_ROLES = frozenset([VIEWER_ROLE_LEAD_GM, VIEWER_ROLE_STAFF])


def serialize_story_log(
    *,
    story: Story,
    progress: AnyStoryProgress | None,
    viewer_role: str,
) -> list[StoryLogBeatEntry | StoryLogEpisodeEntry]:
    """Build the chronological log entries for a story, filtered per role.

    Returns a list mixing StoryLogBeatEntry and StoryLogEpisodeEntry,
    ordered by timestamp (oldest first).

    viewer_role: "staff" | "lead_gm" | "player" | "no_access"
        "no_access" returns an empty list.
    """
    if viewer_role == VIEWER_ROLE_NO_ACCESS:
        return []

    beat_entries = _collect_beat_entries(story=story, progress=progress, viewer_role=viewer_role)
    episode_entries = _collect_episode_entries(
        story=story, progress=progress, viewer_role=viewer_role
    )

    def _sort_key(entry: StoryLogBeatEntry | StoryLogEpisodeEntry) -> datetime:
        if isinstance(entry, StoryLogBeatEntry):
            return entry.completion.recorded_at
        return entry.resolution.resolved_at

    return sorted([*beat_entries, *episode_entries], key=_sort_key)


def _collect_beat_entries(
    *,
    story: Story,
    progress: AnyStoryProgress | None,
    viewer_role: str,
) -> list[StoryLogBeatEntry]:
    completions_qs = BeatCompletion.objects.filter(
        beat__episode__chapter__story=story,
    ).select_related("beat", "beat__episode", "beat__episode__chapter")

    # For players, scope to their own character's completions.
    if viewer_role == VIEWER_ROLE_PLAYER and progress is not None:
        character_sheet = getattr(progress, "character_sheet", None)  # noqa: GETATTR_LITERAL
        if character_sheet is not None:
            completions_qs = completions_qs.filter(character_sheet=character_sheet)

    is_privileged = viewer_role in _PRIVILEGED_ROLES

    entries: list[StoryLogBeatEntry] = []
    for completion in completions_qs:
        beat = completion.beat

        # SECRET beats surface on completion (author-controlled vagueness).
        # For players, the player_hint is suppressed — only resolution text shows.
        if viewer_role == VIEWER_ROLE_PLAYER and beat.visibility == BeatVisibility.SECRET:
            player_hint = ""
        else:
            player_hint = beat.player_hint

        entries.append(
            StoryLogBeatEntry(
                beat=beat,
                completion=completion,
                visible_player_hint=player_hint,
                visible_player_resolution_text=beat.player_resolution_text,
                visible_internal_description=beat.internal_description if is_privileged else None,
                visible_gm_notes=completion.gm_notes if is_privileged else None,
            )
        )
    return entries


def _collect_episode_entries(
    *,
    story: Story,
    progress: AnyStoryProgress | None,
    viewer_role: str,
) -> list[StoryLogEpisodeEntry]:
    resolutions_qs = EpisodeResolution.objects.filter(
        episode__chapter__story=story,
    ).select_related(
        "episode",
        "episode__chapter",
        "chosen_transition",
        "chosen_transition__target_episode",
        "chosen_transition__target_episode__chapter",
    )

    # For players, scope to their own character's resolutions.
    if viewer_role == VIEWER_ROLE_PLAYER and progress is not None:
        character_sheet = getattr(progress, "character_sheet", None)  # noqa: GETATTR_LITERAL
        if character_sheet is not None:
            resolutions_qs = resolutions_qs.filter(character_sheet=character_sheet)

    is_privileged = viewer_role in _PRIVILEGED_ROLES

    return [
        StoryLogEpisodeEntry(
            resolution=resolution,
            visible_internal_notes=resolution.gm_notes if is_privileged else None,
        )
        for resolution in resolutions_qs
    ]
