"""Tests for journal models."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.journals.constants import ResponseType
from world.journals.models import JournalEntry, JournalTag


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
