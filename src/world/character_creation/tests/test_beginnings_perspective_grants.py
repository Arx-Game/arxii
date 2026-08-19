"""Perspective-flagged grants land at CG finalize, viewer-only (#3277)."""

from django.test import TestCase

from world.character_creation.factories import CharacterDraftFactory


class BeginningsPerspectiveGrantTests(TestCase):
    """The opining culture's members know its take; other cultures do not."""

    @classmethod
    def setUpTestData(cls):
        from world.character_creation.factories import BeginningsFactory
        from world.codex.factories import BeginningsCodexGrantFactory, CodexEntryFactory

        cls.holder = BeginningsFactory()
        cls.other = BeginningsFactory()
        cls.opinion = CodexEntryFactory()
        BeginningsCodexGrantFactory(beginnings=cls.holder, entry=cls.opinion, is_perspective=True)

    def _make_sheet_with_roster_entry(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import RosterEntryFactory

        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet__character=sheet.character)
        sheet.refresh_from_db()
        return sheet

    def test_holder_culture_knows_its_perspective(self):
        from world.character_creation.services import _finalize_beginnings_codex_grants
        from world.codex.constants import CodexKnowledgeStatus
        from world.codex.models import CharacterCodexKnowledge

        sheet = self._make_sheet_with_roster_entry()
        draft = CharacterDraftFactory(selected_beginnings=self.holder)

        _finalize_beginnings_codex_grants(draft, sheet)

        knowledge = CharacterCodexKnowledge.objects.get(
            roster_entry=sheet.roster_entry, entry=self.opinion
        )
        assert knowledge.status == CodexKnowledgeStatus.KNOWN

    def test_other_culture_does_not_know_it(self):
        from world.character_creation.services import _finalize_beginnings_codex_grants
        from world.codex.models import CharacterCodexKnowledge

        sheet = self._make_sheet_with_roster_entry()
        draft = CharacterDraftFactory(selected_beginnings=self.other)

        _finalize_beginnings_codex_grants(draft, sheet)

        assert not CharacterCodexKnowledge.objects.filter(
            roster_entry=sheet.roster_entry, entry=self.opinion
        ).exists()
