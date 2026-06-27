"""Tests for writeup kudos and complaint service functions (Task 2)."""

from __future__ import annotations

import logging

from django.test import TestCase

from world.progression.factories import KudosSourceCategoryFactory
from world.progression.models import KudosPointsData, KudosTransaction
from world.relationships.constants import (
    RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
    WRITEUP_KUDOS_AMOUNT,
    UpdateVisibility,
)
from world.relationships.exceptions import (
    AlreadyCommendedError,
    CannotCommendOwnWriteupError,
    NotWriteupSubjectError,
    WriteupNotSharedError,
    WriteupNotVisibleError,
)
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import WriteupComplaint, WriteupKudos
from world.relationships.services import file_writeup_complaint, give_writeup_kudos
from world.roster.factories import RosterTenureFactory


def _make_linked_account(character_sheet):
    """Create a RosterTenure that links character_sheet.character to a fresh account."""
    tenure = RosterTenureFactory(roster_entry__character_sheet__character=character_sheet.character)
    return tenure.player_data.account


class GiveWriteupKudosTest(TestCase):
    """Tests for give_writeup_kudos service function."""

    def setUp(self):
        """Set up a SHARED update by author A about subject B, with accounts linked."""
        rel = CharacterRelationshipFactory()
        self.author_sheet = rel.source
        self.subject_sheet = rel.target
        self.author_account = _make_linked_account(self.author_sheet)
        self.subject_account = _make_linked_account(self.subject_sheet)
        self.update = RelationshipUpdateFactory(
            relationship=rel,
            author=self.author_sheet,
            visibility=UpdateVisibility.SHARED,
        )
        # Seed the category; most tests need it present.
        self.category = KudosSourceCategoryFactory(name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY)

    def test_give_kudos_awards_author_once(self):
        """Subject commending a SHARED update creates a WriteupKudos and awards kudos to author."""
        kudos = give_writeup_kudos(giver_account=self.subject_account, writeup=self.update)
        self.assertIsInstance(kudos, WriteupKudos)
        self.assertEqual(kudos.update, self.update)
        self.assertEqual(kudos.account, self.subject_account)
        points = KudosPointsData.objects.get(account=self.author_account)
        self.assertEqual(points.total_earned, WRITEUP_KUDOS_AMOUNT)

    def test_give_kudos_twice_rejected(self):
        """Second commendation by the same account raises AlreadyCommendedError; total unchanged."""
        give_writeup_kudos(giver_account=self.subject_account, writeup=self.update)
        with self.assertRaises(AlreadyCommendedError):
            give_writeup_kudos(giver_account=self.subject_account, writeup=self.update)
        # The first award still stands; no second award fired.
        points = KudosPointsData.objects.get(account=self.author_account)
        self.assertEqual(points.total_earned, WRITEUP_KUDOS_AMOUNT)

    def test_give_kudos_private_rejected(self):
        """PRIVATE visibility raises WriteupNotSharedError before any other check."""
        rel = CharacterRelationshipFactory()
        private_update = RelationshipUpdateFactory(
            relationship=rel,
            author=rel.source,
            visibility=UpdateVisibility.PRIVATE,
        )
        subject_account = _make_linked_account(rel.target)
        with self.assertRaises(WriteupNotSharedError):
            give_writeup_kudos(giver_account=subject_account, writeup=private_update)

    def test_give_kudos_own_writeup_rejected(self):
        """Giver who is the author raises CannotCommendOwnWriteupError."""
        with self.assertRaises(CannotCommendOwnWriteupError):
            give_writeup_kudos(giver_account=self.author_account, writeup=self.update)

    def test_give_kudos_non_subject_rejected(self):
        """Giver who is neither author nor subject raises NotWriteupSubjectError."""
        other_rel = CharacterRelationshipFactory()
        other_account = _make_linked_account(other_rel.source)
        with self.assertRaises(NotWriteupSubjectError):
            give_writeup_kudos(giver_account=other_account, writeup=self.update)

    def test_give_kudos_awarded_anonymously(self):
        """awarded_by must be None — subject identity must not leak to author (ADR-0033)."""
        give_writeup_kudos(giver_account=self.subject_account, writeup=self.update)
        tx = KudosTransaction.objects.get(account=self.author_account)
        self.assertIsNone(tx.awarded_by, "KudosTransaction.awarded_by must be None")

    def test_give_kudos_unseeded_category_warns_skips(self):
        """Absent KudosSourceCategory: WriteupKudos row is created, no award, warning logged."""
        self.category.delete()
        with self.assertLogs("world.relationships.services", level=logging.WARNING) as cm:
            kudos = give_writeup_kudos(giver_account=self.subject_account, writeup=self.update)
        self.assertIsInstance(kudos, WriteupKudos)
        self.assertFalse(KudosPointsData.objects.filter(account=self.author_account).exists())
        self.assertTrue(any(RELATIONSHIP_WRITEUP_KUDOS_CATEGORY in msg for msg in cm.output))


class FileWriteupComplaintTest(TestCase):
    """Tests for file_writeup_complaint service function."""

    def setUp(self):
        """Set up a SHARED update by author A about subject B."""
        rel = CharacterRelationshipFactory()
        self.author_sheet = rel.source
        self.subject_sheet = rel.target
        self.author_account = _make_linked_account(self.author_sheet)
        self.subject_account = _make_linked_account(self.subject_sheet)
        self.shared_update = RelationshipUpdateFactory(
            relationship=rel,
            author=self.author_sheet,
            visibility=UpdateVisibility.SHARED,
        )

    def test_file_complaint_creates_row(self):
        """Any account that can view a SHARED writeup may file a complaint; no side effect."""
        # Bystander C — unrelated account; SHARED writeups are visible to all.
        other_rel = CharacterRelationshipFactory()
        bystander_account = _make_linked_account(other_rel.source)

        complaint = file_writeup_complaint(
            complainant_account=bystander_account,
            writeup=self.shared_update,
            reason="This writeup is fabricated.",
        )

        self.assertIsInstance(complaint, WriteupComplaint)
        self.assertFalse(complaint.resolved)
        self.assertEqual(complaint.complainant, bystander_account)
        self.assertEqual(complaint.update, self.shared_update)
        self.assertEqual(complaint.reason, "This writeup is fabricated.")

    def test_file_complaint_unviewable_rejected(self):
        """PRIVATE writeup + non-party complainant raises WriteupNotVisibleError."""
        rel = CharacterRelationshipFactory()
        private_update = RelationshipUpdateFactory(
            relationship=rel,
            author=rel.source,
            visibility=UpdateVisibility.PRIVATE,
        )
        # Bystander has no link to either party on this private update.
        other_rel = CharacterRelationshipFactory()
        bystander_account = _make_linked_account(other_rel.source)

        with self.assertRaises(WriteupNotVisibleError):
            file_writeup_complaint(
                complainant_account=bystander_account,
                writeup=private_update,
                reason="Complaint about a private writeup.",
            )
