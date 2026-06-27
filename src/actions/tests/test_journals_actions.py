"""Unit tests for the journal Actions (#1350)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.journals import (
    CreateJournalEntryAction,
    EditJournalEntryAction,
    RespondToJournalAction,
)
from actions.registry import get_action
from actions.types import ActionResult
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.journals.factories import JournalEntryFactory
from world.journals.models import JournalEntry


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class CreateJournalEntryActionTests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.actor = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.actor)

    def test_registry_key_present(
        self,
        mock_award,
        mock_stat,
    ) -> None:
        assert get_action("create_journal_entry") == CreateJournalEntryAction()

    def test_creates_entry_with_tags(
        self,
        mock_award,
        mock_stat,
    ) -> None:
        result: ActionResult = CreateJournalEntryAction().execute(
            actor=self.actor,
            title="A Title",
            body="Some body text.",
            is_public=True,
            tags=["rumor", "court"],
        )
        assert result.success
        entry = JournalEntry.objects.get(author=self.sheet, title="A Title")
        assert entry.is_public is True
        tag_names = {t.name for t in entry.tags.all()}
        assert tag_names == {"rumor", "court"}

    def test_no_active_character_fails(
        self,
        mock_award,
        mock_stat,
    ) -> None:
        bare = CharacterFactory()  # no sheet
        result = CreateJournalEntryAction().execute(
            actor=bare, title="X", body="Y", is_public=False
        )
        assert not result.success
        assert "character" in (result.message or "").lower()


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class RespondToJournalActionTests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.author = CharacterFactory()
        self.author_sheet = CharacterSheetFactory(character=self.author)
        self.responder = CharacterFactory()
        self.responder_sheet = CharacterSheetFactory(character=self.responder)
        self.entry = JournalEntryFactory(author=self.author_sheet, is_public=True)

    def test_respond_creates_praise(
        self,
        mock_award,
        mock_stat,
    ) -> None:
        result = RespondToJournalAction().execute(
            actor=self.responder,
            parent_id=self.entry.pk,
            response_type="praise",
            title="Well said",
            body="I concur.",
        )
        assert result.success
        response = JournalEntry.objects.get(parent=self.entry, response_type="praise")
        assert response.author == self.responder_sheet

    def test_cannot_respond_to_own_entry(
        self,
        mock_award,
        mock_stat,
    ) -> None:
        result = RespondToJournalAction().execute(
            actor=self.author,
            parent_id=self.entry.pk,
            response_type="praise",
            title="x",
            body="y",
        )
        assert not result.success
        assert "own" in (result.message or "").lower()

    def test_unknown_entry_fails(
        self,
        mock_award,
        mock_stat,
    ) -> None:
        result = RespondToJournalAction().execute(
            actor=self.responder,
            parent_id=99999,
            response_type="praise",
            title="x",
            body="y",
        )
        assert not result.success


class EditJournalEntryActionTests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.author = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.author)
        self.entry = JournalEntryFactory(author=self.sheet, title="Old", body="Old body")

    def test_edit_updates_body(self) -> None:
        result = EditJournalEntryAction().execute(
            actor=self.author, entry_id=self.entry.pk, body="New body"
        )
        assert result.success
        self.entry.refresh_from_db()
        assert self.entry.body == "New body"
        assert self.entry.title == "Old"

    def test_cannot_edit_others_entry(self) -> None:
        other = CharacterFactory()
        CharacterSheetFactory(character=other)
        result = EditJournalEntryAction().execute(
            actor=other, entry_id=self.entry.pk, body="hacked"
        )
        assert not result.success
