"""Service functions for Story.primary_table assignment."""

from __future__ import annotations

from django.db import transaction

from world.gm.models import GMTable
from world.stories.models import Story


@transaction.atomic
def assign_story_to_table(*, story: Story, table: GMTable) -> Story:
    """Assign a story to a GM's table. Sets primary_table; clears any prior assignment.

    Service trusts pre-validated inputs — permission gating happens in the
    serializer/view layer per canonical pattern.
    """
    story.primary_table = table
    story.save(update_fields=["primary_table", "updated_at"])
    return story


@transaction.atomic
def detach_story_from_table(*, story: Story) -> Story:
    """Clear the primary_table; story enters 'seeking GM' state.

    Story history and participations are preserved. The story becomes orphaned
    (no active oversight) until a GM accepts it via the Wave 3 offer flow.
    """
    story.primary_table = None
    story.save(update_fields=["primary_table", "updated_at"])
    return story
