"""Story participation service functions."""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from world.magic.exceptions import ProtagonismLockedError
from world.stories.models import Story, StoryParticipation


def create_story_participation(
    story: Story,
    character: ObjectDB,
    participation_level: str,
) -> StoryParticipation:
    """Create a StoryParticipation record for a character.

    Raises:
        ProtagonismLockedError: If the character's sheet is in the terminal
            corruption stage (stage 5), blocking all protagonist-track actions.
    """

    sheet = character.character_sheet
    if sheet is None:
        msg = "Only sheet-backed characters can join stories."
        raise ValueError(msg)

    if sheet.is_protagonism_locked:
        raise ProtagonismLockedError

    return StoryParticipation.objects.create(
        story=story,
        character=sheet,
        participation_level=participation_level,
    )
