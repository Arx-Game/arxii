"""Tests for writeup kudos/complaint API endpoints and read serializer fields (Task 4).

TDD: write failing tests first, then implement.

Covers:
- POST /relationship-updates/kudos/ — subject gives kudos, duplicate rejected, non-subject rejected
- POST /relationship-updates/complaint/ — bystander files complaint, response ok
- Serializer fields: kudos_count + viewer_has_kudosed on all three writeup serializers
- Complaints do NOT appear in any read serializer
"""

from __future__ import annotations

from types import SimpleNamespace

from django.db.models import Count, Exists, OuterRef
from django.test import TestCase
from evennia.utils.idmapper.models import flush_cache
from rest_framework.test import APIRequestFactory, force_authenticate

from world.progression.factories import KudosSourceCategoryFactory
from world.relationships.constants import RELATIONSHIP_WRITEUP_KUDOS_CATEGORY, UpdateVisibility
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipDevelopmentFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import WriteupComplaint, WriteupKudos
from world.relationships.serializers import (
    RelationshipCapstoneSerializer,
    RelationshipDevelopmentSerializer,
    RelationshipUpdateSerializer,
)
from world.relationships.views import RelationshipUpdateViewSet
from world.roster.factories import RosterTenureFactory


def _make_linked_account(character_sheet):
    """Create a RosterTenure linking character_sheet.character to a fresh account."""
    tenure = RosterTenureFactory(roster_entry__character_sheet__character=character_sheet.character)
    return tenure.player_data.account


def _puppet_user(character):
    """Fake authenticated user whose ``puppet`` is ``character``.

    Sets ``pk`` to ``character.db_account_id`` (typically None in factory-built
    characters) to satisfy ``_resolve_actor``'s identity check: the comparison
    ``sheet.character.db_account_id != request.user.pk`` evaluates to
    ``None != None`` → False (passes) when both are None.

    The actual account used by ``get_account_for_character`` is resolved via
    RosterTenure, independently of this pk.
    """
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
    )


class WriteupKudosAPITest(TestCase):
    """Drive the kudos endpoint via the web API."""

    def setUp(self) -> None:
        flush_cache()
        # Relationship: author (source) wrote about subject (target).
        rel = CharacterRelationshipFactory()
        self.author_sheet = rel.source
        self.subject_sheet = rel.target

        # Link both to accounts via RosterTenure so give_writeup_kudos can resolve them.
        self.author_account = _make_linked_account(self.author_sheet)
        self.subject_account = _make_linked_account(self.subject_sheet)

        # A SHARED update (subject can commend it).
        self.update = RelationshipUpdateFactory(
            relationship=rel,
            author=self.author_sheet,
            visibility=UpdateVisibility.SHARED,
        )

        # A bystander character + account for complaint / non-subject tests.
        rel2 = CharacterRelationshipFactory()
        self.bystander_sheet = rel2.source
        self.bystander_account = _make_linked_account(self.bystander_sheet)

        # Seed KudosSourceCategory so award_kudos fires without warnings.
        KudosSourceCategoryFactory(name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY)

        self.factory = APIRequestFactory()

    def _post(self, endpoint: str, user, payload: dict):
        url = f"/api/relationships/relationship-updates/{endpoint}/"
        request = self.factory.post(url, payload, format="json")
        force_authenticate(request, user=user)
        view = RelationshipUpdateViewSet.as_view({"post": endpoint})
        return view(request)

    # --- kudos endpoint ---

    def test_subject_gives_kudos_returns_200(self) -> None:
        """Subject of the writeup can commend it; response is 200 with kudos_id."""
        user = _puppet_user(self.subject_sheet.character)
        resp = self._post("kudos", user, {"writeup_type": "update", "writeup_id": self.update.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["success"])
        self.assertIn("kudos_id", resp.data["data"])

    def test_subject_giving_kudos_creates_writeupkudos_row(self) -> None:
        """Successful kudos POST creates a WriteupKudos DB row."""
        user = _puppet_user(self.subject_sheet.character)
        self._post("kudos", user, {"writeup_type": "update", "writeup_id": self.update.pk})
        self.assertTrue(
            WriteupKudos.objects.filter(account=self.subject_account, update=self.update).exists()
        )

    def test_duplicate_kudos_returns_400_with_user_message(self) -> None:
        """A second kudos POST from the same account returns 400 with the service user_message."""
        # Pre-create the kudos row so the second attempt triggers AlreadyCommendedError.
        WriteupKudos.objects.create(account=self.subject_account, update=self.update)
        user = _puppet_user(self.subject_sheet.character)
        resp = self._post("kudos", user, {"writeup_type": "update", "writeup_id": self.update.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data["success"])
        # The message should come from AlreadyCommendedError.user_message, not str(exc).
        self.assertIn("already", resp.data["message"].lower())

    def test_non_subject_kudos_returns_400(self) -> None:
        """A bystander (not the writeup's subject) cannot give kudos; 400 returned."""
        user = _puppet_user(self.bystander_sheet.character)
        resp = self._post("kudos", user, {"writeup_type": "update", "writeup_id": self.update.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data["success"])

    def test_kudos_missing_writeup_type_returns_400(self) -> None:
        """Missing writeup_type fails serializer validation → 400."""
        user = _puppet_user(self.subject_sheet.character)
        resp = self._post("kudos", user, {"writeup_id": self.update.pk})
        self.assertEqual(resp.status_code, 400)

    def test_kudos_invalid_writeup_type_returns_400(self) -> None:
        """Invalid writeup_type choice fails serializer validation → 400."""
        user = _puppet_user(self.subject_sheet.character)
        resp = self._post("kudos", user, {"writeup_type": "bogus", "writeup_id": self.update.pk})
        self.assertEqual(resp.status_code, 400)

    # --- complaint endpoint ---

    def test_bystander_complaint_returns_200(self) -> None:
        """Any viewer can file a complaint; 200 returned."""
        user = _puppet_user(self.bystander_sheet.character)
        resp = self._post(
            "complaint",
            user,
            {
                "writeup_type": "update",
                "writeup_id": self.update.pk,
                "reason": "This writeup is fabricated.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["success"])
        self.assertIn("complaint_id", resp.data["data"])

    def test_bystander_complaint_creates_db_row(self) -> None:
        """Successful complaint POST creates a WriteupComplaint DB row."""
        user = _puppet_user(self.bystander_sheet.character)
        self._post(
            "complaint",
            user,
            {
                "writeup_type": "update",
                "writeup_id": self.update.pk,
                "reason": "Bad faith RP.",
            },
        )
        self.assertTrue(
            WriteupComplaint.objects.filter(
                complainant=self.bystander_account, update=self.update
            ).exists()
        )

    def test_complaint_missing_reason_returns_400(self) -> None:
        """Missing reason fails serializer validation → 400."""
        user = _puppet_user(self.bystander_sheet.character)
        resp = self._post(
            "complaint",
            user,
            {"writeup_type": "update", "writeup_id": self.update.pk},
        )
        self.assertEqual(resp.status_code, 400)


class WriteupReadSerializerFieldsTest(TestCase):
    """Verify kudos_count / viewer_has_kudosed on read serializers; no complaint leakage."""

    def setUp(self) -> None:
        flush_cache()
        rel = CharacterRelationshipFactory()
        self.author_sheet = rel.source
        self.subject_sheet = rel.target
        self.subject_account = _make_linked_account(self.subject_sheet)

        self.update = RelationshipUpdateFactory(
            relationship=rel,
            author=self.author_sheet,
            visibility=UpdateVisibility.SHARED,
        )
        self.development = RelationshipDevelopmentFactory(
            relationship=rel,
            author=self.author_sheet,
        )
        self.capstone = RelationshipCapstoneFactory(
            relationship=rel,
            author=self.author_sheet,
        )

        # Subject gives kudos on all three.
        WriteupKudos.objects.create(account=self.subject_account, update=self.update)
        WriteupKudos.objects.create(account=self.subject_account, development=self.development)
        WriteupKudos.objects.create(account=self.subject_account, capstone=self.capstone)

        # Bystander files a complaint on the update.
        rel2 = CharacterRelationshipFactory()
        self.bystander_account = _make_linked_account(rel2.source)
        WriteupComplaint.objects.create(
            complainant=self.bystander_account,
            update=self.update,
            reason="Test complaint",
        )

        # Mock request for the subject (the viewer who has kudosed).
        self.subject_request = SimpleNamespace(user=SimpleNamespace(pk=self.subject_account.pk))
        # Mock request for a different viewer (has NOT kudosed).
        other_account = _make_linked_account(CharacterRelationshipFactory().source)
        self.other_request = SimpleNamespace(user=SimpleNamespace(pk=other_account.pk))

    def _annotated_update(self, account_pk):
        """Fetch the update with kudos_count and viewer_has_kudosed annotations."""
        from world.relationships.models import RelationshipUpdate

        return RelationshipUpdate.objects.annotate(
            kudos_count=Count("writeupkudos_set"),
            viewer_has_kudosed=Exists(
                WriteupKudos.objects.filter(account_id=account_pk, update=OuterRef("pk"))
            ),
        ).get(pk=self.update.pk)

    def _annotated_development(self, account_pk):
        from world.relationships.models import RelationshipDevelopment

        return RelationshipDevelopment.objects.annotate(
            kudos_count=Count("writeupkudos_set"),
            viewer_has_kudosed=Exists(
                WriteupKudos.objects.filter(account_id=account_pk, development=OuterRef("pk"))
            ),
        ).get(pk=self.development.pk)

    def _annotated_capstone(self, account_pk):
        from world.relationships.models import RelationshipCapstone

        return RelationshipCapstone.objects.annotate(
            kudos_count=Count("writeupkudos_set"),
            viewer_has_kudosed=Exists(
                WriteupKudos.objects.filter(account_id=account_pk, capstone=OuterRef("pk"))
            ),
        ).get(pk=self.capstone.pk)

    # --- update serializer ---

    def test_update_serializer_kudos_count(self) -> None:
        """RelationshipUpdateSerializer exposes kudos_count = 1 for the given update."""
        obj = self._annotated_update(self.subject_account.pk)
        s = RelationshipUpdateSerializer(obj, context={"request": self.subject_request})
        self.assertEqual(s.data["kudos_count"], 1)

    def test_update_serializer_viewer_has_kudosed_true(self) -> None:
        """viewer_has_kudosed=True when the request user has kudosed the update."""
        obj = self._annotated_update(self.subject_account.pk)
        s = RelationshipUpdateSerializer(obj, context={"request": self.subject_request})
        self.assertTrue(s.data["viewer_has_kudosed"])

    def test_update_serializer_viewer_has_kudosed_false(self) -> None:
        """viewer_has_kudosed=False when the request user has NOT kudosed the update."""
        obj = self._annotated_update(self.other_request.user.pk)
        s = RelationshipUpdateSerializer(obj, context={"request": self.other_request})
        self.assertFalse(s.data["viewer_has_kudosed"])

    def test_update_serializer_no_complaint_fields(self) -> None:
        """Complaint data must NOT appear in RelationshipUpdateSerializer."""
        obj = self._annotated_update(self.subject_account.pk)
        s = RelationshipUpdateSerializer(obj, context={"request": self.subject_request})
        fields = set(s.data.keys())
        self.assertNotIn("complaints", fields)
        self.assertNotIn("complaint_count", fields)
        self.assertNotIn("writeupcomplaints", fields)
        self.assertNotIn("writeupcomplaints_count", fields)

    # --- development serializer ---

    def test_development_serializer_kudos_count(self) -> None:
        """RelationshipDevelopmentSerializer exposes kudos_count = 1."""
        obj = self._annotated_development(self.subject_account.pk)
        s = RelationshipDevelopmentSerializer(obj, context={"request": self.subject_request})
        self.assertEqual(s.data["kudos_count"], 1)

    def test_development_serializer_viewer_has_kudosed_true(self) -> None:
        """viewer_has_kudosed=True when the viewer has kudosed the development."""
        obj = self._annotated_development(self.subject_account.pk)
        s = RelationshipDevelopmentSerializer(obj, context={"request": self.subject_request})
        self.assertTrue(s.data["viewer_has_kudosed"])

    def test_development_serializer_viewer_has_kudosed_false(self) -> None:
        """viewer_has_kudosed=False when the viewer has NOT kudosed the development."""
        obj = self._annotated_development(self.other_request.user.pk)
        s = RelationshipDevelopmentSerializer(obj, context={"request": self.other_request})
        self.assertFalse(s.data["viewer_has_kudosed"])

    def test_development_serializer_no_complaint_fields(self) -> None:
        """Complaint data must NOT appear in RelationshipDevelopmentSerializer."""
        obj = self._annotated_development(self.subject_account.pk)
        s = RelationshipDevelopmentSerializer(obj, context={"request": self.subject_request})
        self.assertNotIn("complaints", set(s.data.keys()))

    # --- capstone serializer ---

    def test_capstone_serializer_kudos_count(self) -> None:
        """RelationshipCapstoneSerializer exposes kudos_count = 1."""
        obj = self._annotated_capstone(self.subject_account.pk)
        s = RelationshipCapstoneSerializer(obj, context={"request": self.subject_request})
        self.assertEqual(s.data["kudos_count"], 1)

    def test_capstone_serializer_viewer_has_kudosed_true(self) -> None:
        """viewer_has_kudosed=True when the viewer has kudosed the capstone."""
        obj = self._annotated_capstone(self.subject_account.pk)
        s = RelationshipCapstoneSerializer(obj, context={"request": self.subject_request})
        self.assertTrue(s.data["viewer_has_kudosed"])

    def test_capstone_serializer_viewer_has_kudosed_false(self) -> None:
        """viewer_has_kudosed=False when the viewer has NOT kudosed the capstone."""
        obj = self._annotated_capstone(self.other_request.user.pk)
        s = RelationshipCapstoneSerializer(obj, context={"request": self.other_request})
        self.assertFalse(s.data["viewer_has_kudosed"])

    def test_capstone_serializer_no_complaint_fields(self) -> None:
        """Complaint data must NOT appear in RelationshipCapstoneSerializer."""
        obj = self._annotated_capstone(self.subject_account.pk)
        s = RelationshipCapstoneSerializer(obj, context={"request": self.subject_request})
        self.assertNotIn("complaints", set(s.data.keys()))
