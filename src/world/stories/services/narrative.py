"""Stories → narrative integration helpers.

After a BeatCompletion or EpisodeResolution is committed, stories calls
these helpers to fan out a NarrativeMessage to the scope-appropriate
recipients. Each helper resolves recipients by story scope, composes the
message body, and delegates to world.narrative.services.send_narrative_message.

- CHARACTER scope: one recipient (the story's owning character_sheet).
- GROUP scope: all active GMTableMembership personas' character_sheets.
- GLOBAL scope: all active StoryParticipation members' sheets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.stories.constants import StoryScope

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.stories.models import BeatCompletion, EpisodeResolution, Story
    from world.stories.types import AnyStoryProgress

_DEFAULT_BEAT_TEXT = "A beat has resolved in your story."
_DEFAULT_EPISODE_TEXT = "Your story advances to a new episode."


def notify_beat_completion(
    completion: BeatCompletion,
    progress: AnyStoryProgress,
) -> None:
    """Fan out a NarrativeMessage for a newly-recorded BeatCompletion.

    Body defaults to the beat's player_resolution_text when set,
    otherwise a minimal fallback. Offline recipients stay queued; online
    recipients get a real-time push.
    """
    beat = completion.beat
    story = beat.episode.chapter.story
    recipients = list(_recipients_for_progress(story, progress))
    body = beat.player_resolution_text or _DEFAULT_BEAT_TEXT

    send_narrative_message(
        recipients=recipients,
        body=body,
        category=NarrativeCategory.STORY,
        related_story=story,
        related_beat_completion=completion,
    )


def notify_episode_resolution(
    resolution: EpisodeResolution,
    progress: AnyStoryProgress,
) -> None:
    """Fan out a NarrativeMessage for a newly-recorded EpisodeResolution.

    Body composes connection_type + connection_summary when a transition
    fired; falls back to the episode's summary or a generic line when
    the resolution parked at a frontier (no transition) or when the
    transition lacks narrative text.
    """
    story = progress.story
    recipients = list(_recipients_for_progress(story, progress))
    body = _render_episode_resolution_text(resolution)

    send_narrative_message(
        recipients=recipients,
        body=body,
        category=NarrativeCategory.STORY,
        related_story=story,
        related_episode_resolution=resolution,
    )


def _recipients_for_progress(
    story: Story,
    progress: AnyStoryProgress,
) -> Iterable[CharacterSheet]:
    """Yield the scope-appropriate recipient sheets for a progress record.

    CHARACTER: the story's owning character_sheet.
    GROUP: active GMTableMembership personas' character_sheets.
    GLOBAL: active StoryParticipation members' sheets.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    match story.scope:
        case StoryScope.CHARACTER:
            if progress.character_sheet_id:
                yield progress.character_sheet
        case StoryScope.GROUP:
            table = progress.gm_table
            memberships = table.memberships.filter(left_at__isnull=True).select_related(
                "persona__character_sheet",
            )
            for membership in memberships:
                persona = membership.persona
                if persona.character_sheet_id:
                    yield persona.character_sheet
        case StoryScope.GLOBAL:
            participations = story.participants.filter(is_active=True).select_related(
                "character",
            )
            for participation in participations:
                try:
                    yield participation.character.sheet_data
                except CharacterSheet.DoesNotExist:
                    continue


def _render_episode_resolution_text(resolution: EpisodeResolution) -> str:
    """Compose a player-facing line for an episode resolution.

    When a transition fired and has a connection_summary, use that.
    When the resolution parked at a frontier (no transition) or the
    transition lacks summary text, fall back to the episode's summary.
    If neither is available, return a minimal default.
    """
    transition = resolution.chosen_transition
    if transition is not None and transition.connection_summary:
        return transition.connection_summary
    episode_summary = resolution.episode.summary
    if episode_summary:
        return episode_summary
    return _DEFAULT_EPISODE_TEXT
