"""Tests for leave_table auto-detach of CHARACTER-scope personal stories.

Wave 2, Task 2.2: When a member leaves a table, their CHARACTER-scope stories
at that table have their primary_table cleared (non-destructively). GROUP-scope
stories at the table are not affected.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import (
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.scenes.factories import PersonaFactory
from world.stories.constants import StoryScope
from world.stories.factories import StoryFactory


def _sheet_for_persona(persona):
    """Return the CharacterSheet for a given Persona."""
    return persona.character_sheet


class LeaveTableAutoDetachTest(TestCase):
    """leave_table detaches the leaving member's CHARACTER-scope stories."""

    def _make_member(self, table):
        """Build a (persona, membership) pair with a full character_sheet chain."""
        char = CharacterFactory()
        sheet = CharacterSheetFactory(character=char)
        persona = PersonaFactory(character_sheet=sheet)
        membership = GMTableMembershipFactory(table=table, persona=persona)
        return persona, membership, sheet

    def test_character_scope_story_detached_on_leave(self):
        """A CHARACTER-scope story at the table has primary_table cleared."""
        from world.gm.services import leave_table

        table = GMTableFactory()
        _persona, membership, sheet = self._make_member(table)
        story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            primary_table=table,
        )
        leave_table(membership)

        story.refresh_from_db()
        assert story.primary_table_id is None
        membership.refresh_from_db()
        assert membership.left_at is not None

    def test_member_with_no_stories_leaves_cleanly(self):
        """A member with no personal stories leaves without error."""
        from world.gm.services import leave_table

        table = GMTableFactory()
        _, membership, _ = self._make_member(table)
        leave_table(membership)

        membership.refresh_from_db()
        assert membership.left_at is not None

    def test_multiple_character_scope_stories_all_detached(self):
        """All CHARACTER-scope stories at the same table are detached."""
        from world.gm.services import leave_table

        table = GMTableFactory()
        _persona, membership, sheet = self._make_member(table)
        story1 = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            primary_table=table,
        )
        story2 = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            primary_table=table,
        )
        leave_table(membership)

        story1.refresh_from_db()
        story2.refresh_from_db()
        assert story1.primary_table_id is None
        assert story2.primary_table_id is None

    def test_story_at_different_table_not_affected(self):
        """A CHARACTER-scope story at a different table is not detached."""
        from world.gm.services import leave_table

        table = GMTableFactory()
        other_table = GMTableFactory()
        _persona, membership, sheet = self._make_member(table)
        story_elsewhere = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            primary_table=other_table,
        )
        leave_table(membership)

        story_elsewhere.refresh_from_db()
        assert story_elsewhere.primary_table_id == other_table.pk

    def test_group_scope_story_at_table_not_detached(self):
        """GROUP-scope stories at the table are not affected by a member's leave."""
        from world.gm.services import leave_table

        table = GMTableFactory()
        _, membership, _ = self._make_member(table)
        group_story = StoryFactory(
            scope=StoryScope.GROUP,
            character_sheet=None,
            primary_table=table,
        )
        leave_table(membership)

        group_story.refresh_from_db()
        assert group_story.primary_table_id == table.pk

    def test_leave_is_noop_if_already_left(self):
        """leave_table is a no-op if the member already left; no double-detach."""
        from django.utils import timezone

        from world.gm.services import leave_table

        table = GMTableFactory()
        _persona, membership, sheet = self._make_member(table)
        story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            primary_table=table,
        )
        # Pre-mark left
        membership.left_at = timezone.now()
        membership.save(update_fields=["left_at"])

        # Calling again should be a no-op: story stays wherever it is
        leave_table(membership)

        # Story was not re-attached, and primary_table was not cleared by the second call
        # (it already was None — but importantly no exception is raised)
        story.refresh_from_db()
        # primary_table is still table because the service returned early before detaching
        assert story.primary_table_id == table.pk
