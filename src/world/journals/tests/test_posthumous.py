"""Tests for the black-journal afterlife: reveal + bequest grants (#3287)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import PosthumousJournalDisposition
from world.estates.factories import EstateSettlementFactory
from world.journals.constants import PosthumousOverride
from world.journals.factories import JournalEntryFactory
from world.journals.models import JournalBequestGrant
from world.journals.services import (
    entry_visible_via_bequest,
    grant_journal_bequest,
    has_journal_bequest_grant,
    reveal_journals_for_settlement,
)


class RevealJournalsForSettlementTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory(
            posthumous_journal_disposition=PosthumousJournalDisposition.REVEAL
        )
        self.settlement = EstateSettlementFactory(character_sheet=self.sheet)

    def test_inherit_entry_reveals_when_sheet_default_is_reveal(self) -> None:
        entry = JournalEntryFactory(author=self.sheet, is_public=False)
        count = reveal_journals_for_settlement(self.sheet, self.settlement)
        entry.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertIsNotNone(entry.revealed_at)
        self.assertEqual(entry.revealed_by_settlement, self.settlement)
        self.assertFalse(entry.is_public)  # a reveal never mutates is_public

    def test_per_entry_seal_override_beats_sheet_reveal_default(self) -> None:
        entry = JournalEntryFactory(
            author=self.sheet, is_public=False, posthumous_override=PosthumousOverride.SEAL
        )
        reveal_journals_for_settlement(self.sheet, self.settlement)
        entry.refresh_from_db()
        self.assertIsNone(entry.revealed_at)

    def test_per_entry_reveal_override_beats_sheet_seal_default(self) -> None:
        self.sheet.posthumous_journal_disposition = PosthumousJournalDisposition.SEAL
        self.sheet.save(update_fields=["posthumous_journal_disposition"])
        entry = JournalEntryFactory(
            author=self.sheet, is_public=False, posthumous_override=PosthumousOverride.REVEAL
        )
        reveal_journals_for_settlement(self.sheet, self.settlement)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.revealed_at)

    def test_sheet_default_seal_leaves_inherit_entries_unrevealed(self) -> None:
        self.sheet.posthumous_journal_disposition = PosthumousJournalDisposition.SEAL
        self.sheet.save(update_fields=["posthumous_journal_disposition"])
        entry = JournalEntryFactory(author=self.sheet, is_public=False)
        reveal_journals_for_settlement(self.sheet, self.settlement)
        entry.refresh_from_db()
        self.assertIsNone(entry.revealed_at)

    def test_public_entries_never_touched(self) -> None:
        """Only private entries are candidates -- a public entry is already visible."""
        entry = JournalEntryFactory(author=self.sheet, is_public=True)
        reveal_journals_for_settlement(self.sheet, self.settlement)
        entry.refresh_from_db()
        self.assertIsNone(entry.revealed_at)

    def test_idempotent_second_call_is_a_no_op(self) -> None:
        JournalEntryFactory(author=self.sheet, is_public=False)
        first_count = reveal_journals_for_settlement(self.sheet, self.settlement)
        second_count = reveal_journals_for_settlement(self.sheet, self.settlement)
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)

    def test_other_sheets_entries_untouched(self) -> None:
        other_sheet = CharacterSheetFactory(
            posthumous_journal_disposition=PosthumousJournalDisposition.REVEAL
        )
        other_entry = JournalEntryFactory(author=other_sheet, is_public=False)
        reveal_journals_for_settlement(self.sheet, self.settlement)
        other_entry.refresh_from_db()
        self.assertIsNone(other_entry.revealed_at)


class JournalBequestGrantServiceTests(TestCase):
    def setUp(self) -> None:
        self.deceased = CharacterSheetFactory()
        self.recipient = CharacterSheetFactory()
        self.settlement = EstateSettlementFactory(character_sheet=self.deceased)

    def test_grant_created(self) -> None:
        grant = grant_journal_bequest(
            recipient_sheet=self.recipient,
            deceased_sheet=self.deceased,
            settlement=self.settlement,
        )
        self.assertTrue(JournalBequestGrant.objects.filter(pk=grant.pk).exists())
        self.assertTrue(
            has_journal_bequest_grant(
                recipient_sheet=self.recipient, deceased_sheet_id=self.deceased.pk
            )
        )

    def test_idempotent_per_recipient_deceased_pair(self) -> None:
        grant_journal_bequest(
            recipient_sheet=self.recipient,
            deceased_sheet=self.deceased,
            settlement=self.settlement,
        )
        grant_journal_bequest(
            recipient_sheet=self.recipient,
            deceased_sheet=self.deceased,
            settlement=self.settlement,
        )
        self.assertEqual(
            JournalBequestGrant.objects.filter(
                recipient_sheet=self.recipient, deceased_sheet=self.deceased
            ).count(),
            1,
        )

    def test_no_grant_means_no_access(self) -> None:
        self.assertFalse(
            has_journal_bequest_grant(
                recipient_sheet=self.recipient, deceased_sheet_id=self.deceased.pk
            )
        )

    def test_seal_beats_grant(self) -> None:
        grant_journal_bequest(
            recipient_sheet=self.recipient,
            deceased_sheet=self.deceased,
            settlement=self.settlement,
        )
        sealed_entry = JournalEntryFactory(
            author=self.deceased,
            is_public=False,
            posthumous_override=PosthumousOverride.SEAL,
        )
        self.assertFalse(entry_visible_via_bequest(sealed_entry, self.recipient))

    def test_non_sealed_private_entry_visible_via_grant(self) -> None:
        grant_journal_bequest(
            recipient_sheet=self.recipient,
            deceased_sheet=self.deceased,
            settlement=self.settlement,
        )
        entry = JournalEntryFactory(author=self.deceased, is_public=False)
        self.assertTrue(entry_visible_via_bequest(entry, self.recipient))

    def test_no_grant_denies_bequest_visibility(self) -> None:
        entry = JournalEntryFactory(author=self.deceased, is_public=False)
        self.assertFalse(entry_visible_via_bequest(entry, self.recipient))

    def test_none_viewer_denied(self) -> None:
        entry = JournalEntryFactory(author=self.deceased, is_public=False)
        self.assertFalse(entry_visible_via_bequest(entry, None))
