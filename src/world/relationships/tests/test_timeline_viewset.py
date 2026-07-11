"""Tests for RelationshipUpdateViewSet's ``timeline`` action (#2159).

Merges Update/Development/Capstone history into one ordered, type-tagged feed with
two mutually exclusive query modes:

- ``?about_character=<sheet_id>`` — writeups about that character from any author,
  visibility-scoped via a generalized (queryset-level) form of
  ``services._can_view_writeup``: non-PRIVATE to anyone, PRIVATE only to the
  author's or the subject's account.
- ``?relationship=<id>`` — the caller must be the relationship's tenure-owned
  source; full history including PRIVATE.

Both/neither params → 400. Ownership is provisioned via ``RosterTenure`` (never
``db_account``, Evennia's live-puppet field), matching Task 1's
``CharacterRelationshipViewSet`` and the existing ``list`` action's convention.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign, UpdateVisibility
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipDevelopmentFactory,
    RelationshipTrackFactory,
    RelationshipUpdateFactory,
)
from world.roster.factories import RosterTenureFactory

TIMELINE_URL = "/api/relationships/relationship-updates/timeline/"


def _make_linked_account(character_sheet):
    """Create a RosterTenure linking character_sheet.character to a fresh account.

    Deliberately does NOT touch ``db_account`` — ownership here is tenure-based,
    matching how ``get_account_for_character`` resolves the acting account.
    """
    tenure = RosterTenureFactory(roster_entry__character_sheet__character=character_sheet.character)
    return tenure.player_data.account


class RelationshipTimelineAboutCharacterTests(TestCase):
    """Tests for ``?about_character=`` mode."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up an author, a subject, a stranger, and one writeup of each kind/visibility."""
        cls.subject_sheet = CharacterSheetFactory()
        cls.subject_account = _make_linked_account(cls.subject_sheet)

        cls.author_sheet = CharacterSheetFactory()
        cls.author_account = _make_linked_account(cls.author_sheet)

        cls.stranger_sheet = CharacterSheetFactory()
        cls.stranger_account = _make_linked_account(cls.stranger_sheet)

        cls.track = RelationshipTrackFactory(name="TimelineTrack", sign=TrackSign.POSITIVE)

        cls.relationship = CharacterRelationshipFactory(
            source=cls.author_sheet, target=cls.subject_sheet
        )
        # A second relationship about the same subject, different author.
        cls.other_author_sheet = CharacterSheetFactory()
        cls.other_relationship = CharacterRelationshipFactory(
            source=cls.other_author_sheet, target=cls.subject_sheet
        )
        # A relationship NOT about the subject at all — must never appear.
        cls.unrelated_relationship = CharacterRelationshipFactory(
            source=cls.author_sheet, target=cls.stranger_sheet
        )

        cls.shared_update = RelationshipUpdateFactory(
            relationship=cls.relationship,
            author=cls.author_sheet,
            track=cls.track,
            title="Shared Update",
            visibility=UpdateVisibility.SHARED,
        )
        cls.public_development = RelationshipDevelopmentFactory(
            relationship=cls.other_relationship,
            author=cls.other_author_sheet,
            track=cls.track,
            title="Public Development",
            visibility=UpdateVisibility.PUBLIC,
        )
        cls.gossip_capstone = RelationshipCapstoneFactory(
            relationship=cls.relationship,
            author=cls.author_sheet,
            track=cls.track,
            title="Gossip Capstone",
            visibility=UpdateVisibility.GOSSIP,
        )
        cls.private_update = RelationshipUpdateFactory(
            relationship=cls.relationship,
            author=cls.author_sheet,
            track=cls.track,
            title="Private Update",
            visibility=UpdateVisibility.PRIVATE,
        )
        cls.unrelated_update = RelationshipUpdateFactory(
            relationship=cls.unrelated_relationship,
            author=cls.author_sheet,
            track=cls.track,
            title="Unrelated Update",
            visibility=UpdateVisibility.SHARED,
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()

    def _titles(self, response) -> list[str]:
        data = response.data
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        return [row["title"] for row in results]

    def test_non_private_visible_to_stranger(self) -> None:
        """SHARED/PUBLIC/GOSSIP writeups about the subject are visible to any account."""
        self.client.force_authenticate(user=self.stranger_account)
        response = self.client.get(TIMELINE_URL, {"about_character": self.subject_sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        titles = self._titles(response)
        assert "Shared Update" in titles
        assert "Public Development" in titles
        assert "Gossip Capstone" in titles

    def test_private_hidden_from_stranger(self) -> None:
        """PRIVATE writeup about the subject is hidden from an uninvolved account."""
        self.client.force_authenticate(user=self.stranger_account)
        response = self.client.get(TIMELINE_URL, {"about_character": self.subject_sheet.pk})
        assert "Private Update" not in self._titles(response)

    def test_private_visible_to_author(self) -> None:
        """PRIVATE writeup is visible to the writeup's author account."""
        self.client.force_authenticate(user=self.author_account)
        response = self.client.get(TIMELINE_URL, {"about_character": self.subject_sheet.pk})
        assert "Private Update" in self._titles(response)

    def test_private_visible_to_subject(self) -> None:
        """PRIVATE writeup is visible to the writeup's subject account."""
        self.client.force_authenticate(user=self.subject_account)
        response = self.client.get(TIMELINE_URL, {"about_character": self.subject_sheet.pk})
        assert "Private Update" in self._titles(response)

    def test_excludes_writeups_about_a_different_character(self) -> None:
        """Writeups whose relationship target is a different character are excluded."""
        self.client.force_authenticate(user=self.author_account)
        response = self.client.get(TIMELINE_URL, {"about_character": self.subject_sheet.pk})
        assert "Unrelated Update" not in self._titles(response)

    def test_merges_all_three_kinds_tagged_and_ordered(self) -> None:
        """Response merges update/development/capstone rows, each carrying its kind."""
        self.client.force_authenticate(user=self.author_account)
        response = self.client.get(TIMELINE_URL, {"about_character": self.subject_sheet.pk})
        data = response.data
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        by_title = {row["title"]: row for row in results}
        assert by_title["Shared Update"]["kind"] == "update"
        assert by_title["Public Development"]["kind"] == "development"
        assert by_title["Gossip Capstone"]["kind"] == "capstone"
        # Ordered -created_at: capstone (most recently created) should not come
        # after the earlier update row given creation order above.
        created_at_values = [row["created_at"] for row in results]
        assert created_at_values == sorted(created_at_values, reverse=True)

    def test_neither_param_is_400(self) -> None:
        """Omitting both params is a 400."""
        self.client.force_authenticate(user=self.author_account)
        response = self.client.get(TIMELINE_URL)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_both_params_is_400(self) -> None:
        """Providing both params at once is a 400."""
        self.client.force_authenticate(user=self.author_account)
        response = self.client.get(
            TIMELINE_URL,
            {"about_character": self.subject_sheet.pk, "relationship": self.relationship.pk},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_request_rejected(self) -> None:
        """Unauthenticated requests are rejected with 401 or 403."""
        response = self.client.get(TIMELINE_URL, {"about_character": self.subject_sheet.pk})
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class RelationshipTimelineRelationshipTests(TestCase):
    """Tests for ``?relationship=`` mode: source-owner-only, full history incl. PRIVATE."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up a source-owning account, a non-source account, and a PRIVATE writeup."""
        cls.source_sheet = CharacterSheetFactory()
        cls.source_account = _make_linked_account(cls.source_sheet)

        cls.target_sheet = CharacterSheetFactory()
        cls.target_account = _make_linked_account(cls.target_sheet)

        cls.stranger_sheet = CharacterSheetFactory()
        cls.stranger_account = _make_linked_account(cls.stranger_sheet)

        cls.track = RelationshipTrackFactory(name="RelTimelineTrack", sign=TrackSign.POSITIVE)
        cls.relationship = CharacterRelationshipFactory(
            source=cls.source_sheet, target=cls.target_sheet
        )
        cls.private_update = RelationshipUpdateFactory(
            relationship=cls.relationship,
            author=cls.source_sheet,
            track=cls.track,
            title="Private On Relationship",
            visibility=UpdateVisibility.PRIVATE,
        )
        cls.shared_capstone = RelationshipCapstoneFactory(
            relationship=cls.relationship,
            author=cls.source_sheet,
            track=cls.track,
            title="Shared Capstone On Relationship",
            visibility=UpdateVisibility.SHARED,
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()

    def _titles(self, response) -> list[str]:
        data = response.data
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        return [row["title"] for row in results]

    def test_source_owner_sees_full_history_incl_private(self) -> None:
        """The relationship's tenure-owned source sees PRIVATE rows too."""
        self.client.force_authenticate(user=self.source_account)
        response = self.client.get(TIMELINE_URL, {"relationship": self.relationship.pk})
        assert response.status_code == status.HTTP_200_OK
        titles = self._titles(response)
        assert "Private On Relationship" in titles
        assert "Shared Capstone On Relationship" in titles

    def test_non_source_denied(self) -> None:
        """A non-source account (even the target) is denied with 403."""
        self.client.force_authenticate(user=self.target_account)
        response = self.client.get(TIMELINE_URL, {"relationship": self.relationship.pk})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_stranger_denied(self) -> None:
        """An uninvolved account is denied with 403."""
        self.client.force_authenticate(user=self.stranger_account)
        response = self.client.get(TIMELINE_URL, {"relationship": self.relationship.pk})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_missing_relationship_is_404(self) -> None:
        """A nonexistent relationship pk is a 404."""
        self.client.force_authenticate(user=self.source_account)
        response = self.client.get(TIMELINE_URL, {"relationship": 999_999})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_neither_param_is_400(self) -> None:
        """Omitting both params is a 400."""
        self.client.force_authenticate(user=self.source_account)
        response = self.client.get(TIMELINE_URL)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_integer_relationship_param_is_400(self) -> None:
        """A non-integer relationship value is a 400, not a 500."""
        self.client.force_authenticate(user=self.source_account)
        response = self.client.get(TIMELINE_URL, {"relationship": "not-a-number"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
