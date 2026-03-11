"""Tests for journal models."""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.journals.constants import ResponseType
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

    def test_needs_reset_after_a_week(self) -> None:
        tracker = WeeklyJournalXP.objects.create(character_sheet=self.sheet)
        tracker.week_reset_at = timezone.now() - timedelta(days=8)
        tracker.save()
        self.assertTrue(tracker.needs_reset())

    def test_no_reset_needed_within_week(self) -> None:
        tracker = WeeklyJournalXP.objects.create(character_sheet=self.sheet)
        self.assertFalse(tracker.needs_reset())

    def test_reset_clears_counters(self) -> None:
        tracker = WeeklyJournalXP.objects.create(
            character_sheet=self.sheet,
            posts_this_week=3,
            praised_this_week=True,
            was_praised_this_week=True,
            retorted_this_week=True,
            was_retorted_this_week=True,
        )
        tracker.reset_week()
        self.assertEqual(tracker.posts_this_week, 0)
        self.assertFalse(tracker.praised_this_week)
        self.assertFalse(tracker.was_praised_this_week)
        self.assertFalse(tracker.retorted_this_week)
        self.assertFalse(tracker.was_retorted_this_week)

    def test_unique_per_character(self) -> None:
        WeeklyJournalXP.objects.create(character_sheet=self.sheet)
        with self.assertRaises(IntegrityError):
            WeeklyJournalXP.objects.create(character_sheet=self.sheet)
