"""Tests for journal models."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import RetortConsent
from world.journals.constants import INTRODUCTION_KINDS, JournalKind, ResponseType
from world.journals.factories import CondemnFactory, JournalEntryFactory
from world.journals.models import JournalEntry, JournalTag, WeeklyJournalXP


class JournalEntryTests(TestCase):
    """Test JournalEntry model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_create_basic_entry(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="A Day in the City",
            body="The streets were quiet.",
            is_public=True,
        )
        self.assertEqual(entry.title, "A Day in the City")
        self.assertTrue(entry.is_public)
        self.assertIsNone(entry.parent)
        self.assertIsNone(entry.response_type)

    def test_create_private_entry(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="Secret",
            body="Hidden.",
            is_public=False,
        )
        self.assertFalse(entry.is_public)

    def test_create_praise_response(self) -> None:
        parent = JournalEntry.objects.create(
            author=self.sheet,
            title="Original",
            body="Content.",
            is_public=True,
        )
        other = CharacterSheetFactory()
        praise = JournalEntry.objects.create(
            author=other,
            title="Well Said!",
            body="I agree.",
            is_public=True,
            parent=parent,
            response_type=ResponseType.PRAISE,
        )
        self.assertEqual(praise.parent, parent)
        self.assertEqual(praise.response_type, ResponseType.PRAISE)
        self.assertIn(praise, parent.responses.all())

    def test_create_retort_response(self) -> None:
        parent = JournalEntry.objects.create(
            author=self.sheet,
            title="Bold Claim",
            body="I am the greatest.",
            is_public=True,
        )
        rival = CharacterSheetFactory()
        retort = JournalEntry.objects.create(
            author=rival,
            title="Hardly!",
            body="Your arrogance is breathtaking.",
            is_public=True,
            parent=parent,
            response_type=ResponseType.RETORT,
        )
        self.assertEqual(retort.response_type, ResponseType.RETORT)

    def test_str_representation(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="My Title",
            body="Content.",
            is_public=True,
        )
        self.assertIn("My Title", str(entry))

    def test_edited_at_null_on_create(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="Fresh",
            body="New.",
            is_public=True,
        )
        self.assertIsNone(entry.edited_at)


class JournalTagTests(TestCase):
    """Test JournalTag model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_create_tag(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="Battle",
            body="Fought.",
            is_public=True,
        )
        tag = JournalTag.objects.create(entry=entry, name="siege of arx")
        self.assertEqual(tag.name, "siege of arx")
        self.assertIn(tag, entry.tags.all())

    def test_unique_tag_per_entry(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="Tagged",
            body="Content.",
            is_public=True,
        )
        JournalTag.objects.create(entry=entry, name="combat")
        with self.assertRaises(IntegrityError):
            JournalTag.objects.create(entry=entry, name="combat")


class WeeklyJournalXPTests(TestCase):
    """Test WeeklyJournalXP model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_create_tracker(self) -> None:
        tracker = WeeklyJournalXP.objects.create(character_sheet=self.sheet)
        self.assertEqual(tracker.posts_this_week, 0)
        self.assertFalse(tracker.praised_this_week)
        self.assertFalse(tracker.was_praised_this_week)
        self.assertFalse(tracker.retorted_this_week)
        self.assertFalse(tracker.was_retorted_this_week)

    def test_needs_reset_for_different_week(self) -> None:
        from world.game_clock.week_services import advance_game_week, get_current_game_week

        old_week = get_current_game_week()
        tracker = WeeklyJournalXP.objects.create(character_sheet=self.sheet, game_week=old_week)
        new_week = advance_game_week()
        self.assertTrue(tracker.needs_reset(new_week))

    def test_no_reset_needed_same_week(self) -> None:
        from world.game_clock.week_services import get_current_game_week

        current_week = get_current_game_week()
        tracker = WeeklyJournalXP.objects.create(character_sheet=self.sheet, game_week=current_week)
        self.assertFalse(tracker.needs_reset(current_week))

    def test_reset_clears_counters(self) -> None:
        from world.game_clock.week_services import advance_game_week, get_current_game_week

        old_week = get_current_game_week()
        tracker = WeeklyJournalXP.objects.create(
            character_sheet=self.sheet,
            game_week=old_week,
            posts_this_week=3,
            praised_this_week=True,
            was_praised_this_week=True,
            retorted_this_week=True,
            was_retorted_this_week=True,
        )
        new_week = advance_game_week()
        tracker.reset_week(new_week)
        self.assertEqual(tracker.posts_this_week, 0)
        self.assertFalse(tracker.praised_this_week)
        self.assertFalse(tracker.was_praised_this_week)
        self.assertFalse(tracker.retorted_this_week)
        self.assertFalse(tracker.was_retorted_this_week)
        self.assertEqual(tracker.game_week, new_week)

    def test_unique_per_character(self) -> None:
        WeeklyJournalXP.objects.create(character_sheet=self.sheet)
        with self.assertRaises(IntegrityError):
            WeeklyJournalXP.objects.create(character_sheet=self.sheet)


class AboutAndConsentColumnsTest(TestCase):
    def test_entry_about_defaults_null_and_holds_a_sheet(self) -> None:
        subject = CharacterSheetFactory()
        entry = JournalEntryFactory()
        self.assertIsNone(entry.about)
        entry.about = subject
        entry.save(update_fields=["about"])
        entry.refresh_from_db()
        self.assertEqual(entry.about_id, subject.pk)
        self.assertIn(entry, subject.journal_entries_about.all())

    def test_deleting_the_subject_keeps_the_entry(self) -> None:
        subject = CharacterSheetFactory()
        entry = JournalEntryFactory(about=subject)
        subject.delete()
        # flush_from_cache(): the collector's SET_NULL is a bulk UPDATE, which never
        # touches this identity-mapped Python instance, and refresh_from_db() alone
        # would just short-circuit back to the same cached (stale) instance (idmapper
        # quirk documented for e.g. world/magic/tests/test_audere_majora_offer.py).
        entry.flush_from_cache()
        entry.refresh_from_db()
        self.assertIsNone(entry.about_id)

    def test_sheet_consent_defaults_to_rivals(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertEqual(sheet.retort_consent, RetortConsent.RIVALS)
        self.assertIsNone(sheet.journals_visited_at)

    def test_condemn_is_a_response_type(self) -> None:
        response = CondemnFactory()
        self.assertEqual(response.response_type, ResponseType.CONDEMN)
        self.assertIsNotNone(response.parent_id)

    def test_introduction_kinds_are_the_three_non_entry_kinds(self) -> None:
        self.assertEqual(
            set(INTRODUCTION_KINDS),
            {JournalKind.FIRST_JOURNAL, JournalKind.APPLICATION, JournalKind.WHISPERS},
        )
