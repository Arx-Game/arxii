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
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except (CharacterSheet.DoesNotExist, AttributeError):
        sheet = None

    if sheet is not None and sheet.is_protagonism_locked:
        raise ProtagonismLockedError

    return StoryParticipation.objects.create(
        story=story,
        character=character,
        participation_level=participation_level,
    )
