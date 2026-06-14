"""Tests for _finalize_path_codex_grants: consuming PathCodexGrant at CG finalization."""

from django.test import TestCase

from world.character_creation.factories import CharacterDraftFactory
from world.classes.factories import PathFactory


class FinalizePathCodexGrantsTests(TestCase):
    """Tests for _finalize_path_codex_grants service function."""

    @classmethod
    def setUpTestData(cls):
        from world.codex.factories import CodexEntryFactory, PathCodexGrantFactory

        cls.path = PathFactory()
        cls.codex_entry = CodexEntryFactory()
        PathCodexGrantFactory(path=cls.path, entry=cls.codex_entry)

    def _make_sheet_with_roster_entry(self):
        """Create a CharacterSheet with a wired RosterEntry.

        Mirrors the pattern from test_traditions.py FinalizeMagicTraditionTests:
            sheet = CharacterSheetFactory()
            RosterEntryFactory(character_sheet__character=sheet.character)
            sheet.refresh_from_db()
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import RosterEntryFactory

        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet__character=sheet.character)
        sheet.refresh_from_db()
        return sheet

    def test_creates_codex_knowledge_for_path_grants(self):
        """Grants applied when draft has a selected_path with PathCodexGrant rows."""
        from world.character_creation.services import _finalize_path_codex_grants
        from world.codex.constants import CodexKnowledgeStatus
        from world.codex.models import CharacterCodexKnowledge

        sheet = self._make_sheet_with_roster_entry()
        draft = CharacterDraftFactory(selected_path=self.path)

        _finalize_path_codex_grants(draft, sheet)

        knowledge = CharacterCodexKnowledge.objects.filter(
            roster_entry=sheet.roster_entry,
            entry=self.codex_entry,
        )
        assert knowledge.exists()
        assert knowledge.first().status == CodexKnowledgeStatus.KNOWN

    def test_no_selected_path_is_noop(self):
        """No rows created when draft has no selected_path."""
        from world.character_creation.services import _finalize_path_codex_grants
        from world.codex.models import CharacterCodexKnowledge

        sheet = self._make_sheet_with_roster_entry()
        draft = CharacterDraftFactory(selected_path=None)

        _finalize_path_codex_grants(draft, sheet)

        assert (
            CharacterCodexKnowledge.objects.filter(
                roster_entry=sheet.roster_entry,
            ).count()
            == 0
        )

    def test_idempotent_double_call_creates_one_row(self):
        """Calling _finalize_path_codex_grants twice creates exactly one row per entry."""
        from world.character_creation.services import _finalize_path_codex_grants
        from world.codex.models import CharacterCodexKnowledge

        sheet = self._make_sheet_with_roster_entry()
        draft = CharacterDraftFactory(selected_path=self.path)

        _finalize_path_codex_grants(draft, sheet)
        _finalize_path_codex_grants(draft, sheet)

        count = CharacterCodexKnowledge.objects.filter(
            roster_entry=sheet.roster_entry,
            entry=self.codex_entry,
        ).count()
        assert count == 1
