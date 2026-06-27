"""Tests for WriteupKudos and WriteupComplaint models (Task 1: feedback models)."""

from django.db import IntegrityError
from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipDevelopmentFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import WriteupComplaint, WriteupKudos


def _make_account(n: int) -> AccountDB:
    """Create a minimal AccountDB for test use."""
    return AccountDB.objects.create(
        username=f"testaccount{n}",
        email=f"testaccount{n}@example.com",
    )


class WriteupFeedbackConstraintTests(TestCase):
    """DB-level constraint tests for WriteupKudos (abstract base constraints)."""

    @classmethod
    def setUpTestData(cls):
        relationship = CharacterRelationshipFactory()
        cls.update = RelationshipUpdateFactory(relationship=relationship)
        cls.development = RelationshipDevelopmentFactory(relationship=relationship)
        cls.account = _make_account(1)

    def test_exactly_one_writeup_constraint_rejects_zero(self):
        """Creating WriteupKudos with no writeup FK set must raise IntegrityError."""
        with self.assertRaises(IntegrityError):
            WriteupKudos.objects.create(
                account=self.account,
                update=None,
                development=None,
                capstone=None,
            )

    def test_exactly_one_writeup_constraint_rejects_two(self):
        """Creating WriteupKudos with two writeup FKs set must raise IntegrityError."""
        with self.assertRaises(IntegrityError):
            WriteupKudos.objects.create(
                account=self.account,
                update=self.update,
                development=self.development,
                capstone=None,
            )


class WriteupKudosPropertyTests(TestCase):
    """Tests for WriteupFeedbackBase properties via WriteupKudos."""

    @classmethod
    def setUpTestData(cls):
        cls.relationship = CharacterRelationshipFactory()
        cls.update = RelationshipUpdateFactory(relationship=cls.relationship)
        cls.account = _make_account(2)

    def test_writeup_property_returns_set_one(self):
        """writeup returns the non-null writeup FK (update in this case)."""
        kudos = WriteupKudos.objects.create(account=self.account, update=self.update)
        self.assertEqual(kudos.writeup, self.update)

    def test_author_sheet_returns_writeup_author(self):
        """author_sheet returns the writeup's author CharacterSheet."""
        kudos = WriteupKudos.objects.create(account=self.account, update=self.update)
        self.assertEqual(kudos.author_sheet, self.update.author)

    def test_subject_sheet_returns_relationship_target(self):
        """subject_sheet returns the relationship's target CharacterSheet."""
        kudos = WriteupKudos.objects.create(account=self.account, update=self.update)
        self.assertEqual(kudos.subject_sheet, self.relationship.target)


class WriteupKudosUniqueConstraintTests(TestCase):
    """Tests for per-account-per-writeup uniqueness."""

    @classmethod
    def setUpTestData(cls):
        relationship = CharacterRelationshipFactory()
        cls.update = RelationshipUpdateFactory(relationship=relationship)
        cls.account = _make_account(3)

    def test_unique_kudos_per_account_per_writeup(self):
        """Two WriteupKudos with same account + update must raise IntegrityError."""
        WriteupKudos.objects.create(account=self.account, update=self.update)
        with self.assertRaises(IntegrityError):
            WriteupKudos.objects.create(account=self.account, update=self.update)


class WriteupComplaintTests(TestCase):
    """Tests for WriteupComplaint model fields and defaults."""

    @classmethod
    def setUpTestData(cls):
        relationship = CharacterRelationshipFactory()
        cls.update = RelationshipUpdateFactory(relationship=relationship)
        cls.account = _make_account(4)

    def test_complaint_fields(self):
        """WriteupComplaint stores reason and defaults resolved to False."""
        complaint = WriteupComplaint.objects.create(
            complainant=self.account,
            update=self.update,
            reason="This writeup is fabricated.",
        )
        self.assertFalse(complaint.resolved)
        self.assertEqual(complaint.reason, "This writeup is fabricated.")

    def test_complaint_writeup_property(self):
        """writeup property on complaint also returns the correct writeup."""
        complaint = WriteupComplaint.objects.create(
            complainant=self.account,
            update=self.update,
            reason="x",
        )
        self.assertEqual(complaint.writeup, self.update)


class WriteupFeedbackCapstoneTests(TestCase):
    """Verify feedback works via a capstone writeup too."""

    @classmethod
    def setUpTestData(cls):
        cls.relationship = CharacterRelationshipFactory()
        cls.capstone = RelationshipCapstoneFactory(relationship=cls.relationship)
        cls.account = _make_account(5)

    def test_kudos_via_capstone(self):
        """WriteupKudos can reference a capstone; properties resolve correctly."""
        kudos = WriteupKudos.objects.create(account=self.account, capstone=self.capstone)
        self.assertEqual(kudos.writeup, self.capstone)
        self.assertEqual(kudos.author_sheet, self.capstone.author)
        self.assertEqual(kudos.subject_sheet, self.relationship.target)
