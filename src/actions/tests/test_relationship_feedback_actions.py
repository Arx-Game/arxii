"""Tests for writeup feedback Actions (GiveWriteupKudos + FileWriteupComplaint)."""

from __future__ import annotations

from django.test import TestCase

from actions.tests.utils import ActionTestCase
from world.relationships.constants import UpdateVisibility
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipDevelopmentFactory,
    RelationshipTrackProgressFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import WriteupComplaint, WriteupKudos
from world.roster.factories import RosterTenureFactory


class WriteupFeedbackActionTestCase(ActionTestCase):
    """Extends ActionTestCase with writeup-feedback fixtures.

    actor_account — the account linked to self.actor via an active RosterTenure.
    update        — a SHARED RelationshipUpdate authored by target_sheet about actor_sheet
                    (actor is the subject/target of the writeup).
    """

    def setUp(self) -> None:
        super().setUp()
        # Link actor's character to an account.
        actor_tenure = RosterTenureFactory(roster_entry__character_sheet=self.actor_sheet)
        self.actor_account = actor_tenure.player_data.account

        # A SHARED update authored by target_sheet (source) about actor_sheet (target/subject).
        rel = CharacterRelationshipFactory(source=self.target_sheet, target=self.actor_sheet)
        self.update = RelationshipUpdateFactory(
            relationship=rel,
            author=self.target_sheet,
            visibility=UpdateVisibility.SHARED,
        )
        self.rel = rel


# ---------------------------------------------------------------------------
# GiveWriteupKudosAction
# ---------------------------------------------------------------------------


class GiveWriteupKudosActionTests(WriteupFeedbackActionTestCase):
    """Tests for GiveWriteupKudosAction (key: give_writeup_kudos)."""

    def _action(self):
        from actions.definitions.relationships import GiveWriteupKudosAction

        return GiveWriteupKudosAction()

    # ---- happy path ----

    def test_kudos_created_for_shared_update(self):
        """Giving kudos on a SHARED update creates a WriteupKudos row."""
        result = self._action().run(
            actor=self.actor,
            writeup_type="update",
            writeup_id=self.update.pk,
        )
        self.assertTrue(result.success, result.message)
        self.assertIn("kudos_id", result.data)
        kudos = WriteupKudos.objects.get(pk=result.data["kudos_id"])
        self.assertEqual(kudos.update, self.update)
        self.assertEqual(kudos.account, self.actor_account)

    def test_kudos_created_for_development_writeup(self):
        """Giving kudos on a SHARED development writeup works via writeup_type='development'."""
        progress = RelationshipTrackProgressFactory(
            relationship=self.rel,
            track=self.update.track,
            capacity=10,
            developed_points=0,
        )
        dev = RelationshipDevelopmentFactory(
            relationship=self.rel,
            author=self.target_sheet,
            track=progress.track,
            points_earned=5,
            visibility=UpdateVisibility.SHARED,
        )
        result = self._action().run(
            actor=self.actor,
            writeup_type="development",
            writeup_id=dev.pk,
        )
        self.assertTrue(result.success, result.message)
        kudos = WriteupKudos.objects.get(pk=result.data["kudos_id"])
        self.assertEqual(kudos.development, dev)

    def test_kudos_created_for_capstone_writeup(self):
        """Giving kudos on a SHARED capstone writeup works via writeup_type='capstone'."""
        capstone = RelationshipCapstoneFactory(
            relationship=self.rel,
            author=self.target_sheet,
            track=self.update.track,
            visibility=UpdateVisibility.SHARED,
        )
        result = self._action().run(
            actor=self.actor,
            writeup_type="capstone",
            writeup_id=capstone.pk,
        )
        self.assertTrue(result.success, result.message)
        kudos = WriteupKudos.objects.get(pk=result.data["kudos_id"])
        self.assertEqual(kudos.capstone, capstone)

    # ---- error: missing / invalid kwargs ----

    def test_missing_writeup_type_fails(self):
        """No writeup_type → clean failure."""
        result = self._action().run(actor=self.actor, writeup_id=self.update.pk)
        self.assertFalse(result.success)
        self.assertIn("writeup", result.message.lower())

    def test_missing_writeup_id_fails(self):
        """No writeup_id → clean failure."""
        result = self._action().run(actor=self.actor, writeup_type="update")
        self.assertFalse(result.success)
        self.assertIn("writeup", result.message.lower())

    def test_invalid_writeup_type_fails(self):
        """Unknown writeup_type → clean failure."""
        result = self._action().run(
            actor=self.actor, writeup_type="bogus", writeup_id=self.update.pk
        )
        self.assertFalse(result.success)

    def test_writeup_not_found_fails(self):
        """Non-existent writeup_id → clean failure (no 500)."""
        result = self._action().run(actor=self.actor, writeup_type="update", writeup_id=99999)
        self.assertFalse(result.success)

    # ---- error: service exception paths ----

    def test_private_writeup_fails(self):
        """Trying to commend a PRIVATE writeup surfaces WriteupNotSharedError as a clean message."""
        from world.relationships.factories import RelationshipUpdateFactory

        private_update = RelationshipUpdateFactory(
            relationship=self.rel,
            author=self.target_sheet,
            visibility=UpdateVisibility.PRIVATE,
        )
        result = self._action().run(
            actor=self.actor, writeup_type="update", writeup_id=private_update.pk
        )
        self.assertFalse(result.success)
        self.assertIn("shared", result.message.lower())

    def test_actor_not_subject_fails(self):
        """An account that is not the writeup's subject cannot give kudos."""
        # Create a NEW relationship where actor is NOT the target/subject.
        other_rel = CharacterRelationshipFactory(
            source=self.actor_sheet,
            target=self.target_sheet,
        )
        other_update = RelationshipUpdateFactory(
            relationship=other_rel,
            author=self.actor_sheet,
            visibility=UpdateVisibility.SHARED,
        )
        # actor tries to commend their own writeup (CannotCommendOwnWriteupError takes priority)
        result = self._action().run(
            actor=self.actor, writeup_type="update", writeup_id=other_update.pk
        )
        self.assertFalse(result.success)

    def test_already_commended_fails(self):
        """Second kudos on the same writeup from the same account → AlreadyCommendedError."""
        self._action().run(actor=self.actor, writeup_type="update", writeup_id=self.update.pk)
        result = self._action().run(
            actor=self.actor, writeup_type="update", writeup_id=self.update.pk
        )
        self.assertFalse(result.success)
        self.assertIn("already", result.message.lower())

    # ---- prerequisite: no character sheet ----

    def test_actor_without_sheet_blocked(self):
        """HasCharacterSheetPrerequisite blocks an actor with no attached CharacterSheet."""
        from evennia_extensions.factories import CharacterFactory

        bare_actor = CharacterFactory()
        result = self._action().run(
            actor=bare_actor, writeup_type="update", writeup_id=self.update.pk
        )
        self.assertFalse(result.success)
        self.assertIn("character", result.message.lower())


# ---------------------------------------------------------------------------
# FileWriteupComplaintAction
# ---------------------------------------------------------------------------


class FileWriteupComplaintActionTests(WriteupFeedbackActionTestCase):
    """Tests for FileWriteupComplaintAction (key: file_writeup_complaint)."""

    REASON = "This writeup misrepresents our shared RP."

    def _action(self):
        from actions.definitions.relationships import FileWriteupComplaintAction

        return FileWriteupComplaintAction()

    # ---- happy path ----

    def test_complaint_filed_for_shared_update(self):
        """Filing a complaint on a SHARED update creates a WriteupComplaint row."""
        result = self._action().run(
            actor=self.actor,
            writeup_type="update",
            writeup_id=self.update.pk,
            reason=self.REASON,
        )
        self.assertTrue(result.success, result.message)
        self.assertIn("complaint_id", result.data)
        complaint = WriteupComplaint.objects.get(pk=result.data["complaint_id"])
        self.assertEqual(complaint.update, self.update)
        self.assertEqual(complaint.complainant, self.actor_account)
        self.assertEqual(complaint.reason, self.REASON)
        self.assertFalse(complaint.resolved)

    def test_complaint_filed_for_development_writeup(self):
        """Filing a complaint on a SHARED development writeup works."""
        progress = RelationshipTrackProgressFactory(
            relationship=self.rel,
            track=self.update.track,
            capacity=10,
            developed_points=0,
        )
        dev = RelationshipDevelopmentFactory(
            relationship=self.rel,
            author=self.target_sheet,
            track=progress.track,
            points_earned=5,
            visibility=UpdateVisibility.SHARED,
        )
        result = self._action().run(
            actor=self.actor,
            writeup_type="development",
            writeup_id=dev.pk,
            reason=self.REASON,
        )
        self.assertTrue(result.success, result.message)
        complaint = WriteupComplaint.objects.get(pk=result.data["complaint_id"])
        self.assertEqual(complaint.development, dev)

    def test_complaint_filed_for_capstone_writeup(self):
        """Filing a complaint on a SHARED capstone writeup works."""
        capstone = RelationshipCapstoneFactory(
            relationship=self.rel,
            author=self.target_sheet,
            track=self.update.track,
            visibility=UpdateVisibility.SHARED,
        )
        result = self._action().run(
            actor=self.actor,
            writeup_type="capstone",
            writeup_id=capstone.pk,
            reason=self.REASON,
        )
        self.assertTrue(result.success, result.message)
        complaint = WriteupComplaint.objects.get(pk=result.data["complaint_id"])
        self.assertEqual(complaint.capstone, capstone)

    # ---- error: missing / invalid kwargs ----

    def test_missing_reason_fails(self):
        """No reason → clean failure."""
        result = self._action().run(
            actor=self.actor, writeup_type="update", writeup_id=self.update.pk
        )
        self.assertFalse(result.success)
        self.assertIn("reason", result.message.lower())

    def test_empty_reason_fails(self):
        """Empty string reason → clean failure."""
        result = self._action().run(
            actor=self.actor,
            writeup_type="update",
            writeup_id=self.update.pk,
            reason="",
        )
        self.assertFalse(result.success)
        self.assertIn("reason", result.message.lower())

    def test_missing_writeup_type_fails(self):
        """No writeup_type → clean failure."""
        result = self._action().run(actor=self.actor, writeup_id=self.update.pk, reason=self.REASON)
        self.assertFalse(result.success)

    def test_missing_writeup_id_fails(self):
        """No writeup_id → clean failure."""
        result = self._action().run(actor=self.actor, writeup_type="update", reason=self.REASON)
        self.assertFalse(result.success)

    def test_invalid_writeup_type_fails(self):
        """Unknown writeup_type → clean failure."""
        result = self._action().run(
            actor=self.actor, writeup_type="bogus", writeup_id=self.update.pk, reason=self.REASON
        )
        self.assertFalse(result.success)

    def test_writeup_not_found_fails(self):
        """Non-existent writeup_id → clean failure (no 500)."""
        result = self._action().run(
            actor=self.actor, writeup_type="update", writeup_id=99999, reason=self.REASON
        )
        self.assertFalse(result.success)

    # ---- error: service exception paths ----

    def test_private_writeup_invisible_to_non_party_fails(self):
        """A PRIVATE writeup between two unrelated characters is invisible to the actor."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.relationships.factories import (
            CharacterRelationshipFactory,
            RelationshipUpdateFactory,
        )

        # A PRIVATE relationship between two characters unrelated to actor_sheet.
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        unrelated_rel = CharacterRelationshipFactory(source=sheet_a, target=sheet_b)
        private_update = RelationshipUpdateFactory(
            relationship=unrelated_rel,
            author=sheet_a,
            visibility=UpdateVisibility.PRIVATE,
        )
        result = self._action().run(
            actor=self.actor,
            writeup_type="update",
            writeup_id=private_update.pk,
            reason=self.REASON,
        )
        self.assertFalse(result.success)
        self.assertIn("cannot view", result.message.lower())

    # ---- prerequisite: no character sheet ----

    def test_actor_without_sheet_blocked(self):
        """HasCharacterSheetPrerequisite blocks an actor with no attached CharacterSheet."""
        from evennia_extensions.factories import CharacterFactory

        bare_actor = CharacterFactory()
        result = self._action().run(
            actor=bare_actor,
            writeup_type="update",
            writeup_id=self.update.pk,
            reason=self.REASON,
        )
        self.assertFalse(result.success)
        self.assertIn("character", result.message.lower())


# ---------------------------------------------------------------------------
# Registry smoke tests
# ---------------------------------------------------------------------------


class WriteupFeedbackRegistryTests(TestCase):
    """Verify both actions are registered and have the right keys."""

    def test_give_writeup_kudos_registered(self):
        from actions.registry import get_action

        action = get_action("give_writeup_kudos")
        self.assertIsNotNone(action)
        self.assertEqual(action.key, "give_writeup_kudos")

    def test_file_writeup_complaint_registered(self):
        from actions.registry import get_action

        action = get_action("file_writeup_complaint")
        self.assertIsNotNone(action)
        self.assertEqual(action.key, "file_writeup_complaint")
