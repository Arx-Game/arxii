"""Scope-polymorphic helpers for looking up and advancing story progress.

CHARACTER scope uses StoryProgress (owned by CharacterSheet).
GROUP scope uses GroupStoryProgress (owned by GMTable).
GLOBAL scope uses GlobalStoryProgress (singleton per story).

All three share the same (current_episode, last_advanced_at, is_active)
shape — these helpers abstract over that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.stories.constants import StoryScope

if TYPE_CHECKING:
    from world.stories.models import Episode, Story
    from world.stories.types import AnyStoryProgress


def get_active_progress_for_story(story: Story) -> AnyStoryProgress | None:
    """Return the active progress record for a story, dispatching on scope.

    Returns None if no progress record exists (e.g., GLOBAL story that
    hasn't been started yet, or no characters have begun a CHARACTER story).
    For GROUP scope, returns the first active GroupStoryProgress; if the
    story has multiple GMTables assigned, callers should query more
    specifically.
    """
    from world.stories.models import GlobalStoryProgress  # noqa: PLC0415

    match story.scope:
        case StoryScope.CHARACTER:
            return story.progress_records.filter(is_active=True).first()
        case StoryScope.GROUP:
            return story.group_progress_records.filter(is_active=True).first()
        case StoryScope.GLOBAL:
            try:
                return story.global_progress
            except GlobalStoryProgress.DoesNotExist:
                return None
        case _:
            return None


def advance_progress_to_episode(
    progress: AnyStoryProgress,
    target_episode: Episode | None,
) -> None:
    """Update current_episode on whichever progress type is passed.

    All three progress models have the same (current_episode,
    last_advanced_at auto_now) shape. This wrapper keeps callers free of
    isinstance checks.
    """
    progress.current_episode = target_episode
    progress.save(update_fields=["current_episode", "last_advanced_at"])
