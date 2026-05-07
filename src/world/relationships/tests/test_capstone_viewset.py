"""Tests for RelationshipCapstoneViewSet."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipTrackFactory,
)


class RelationshipCapstoneViewSetTests(TestCase):
    """Tests for RelationshipCapstoneViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data shared across all tests."""
        User = get_user_model()

        # Caller account and their character sheet
        cls.caller_account = User.objects.create_user(
            username="capstone_caller", password="testpass"
        )
        cls.caller_sheet = CharacterSheetFactory()
        cls.caller_sheet.character.db_account = cls.caller_account
        cls.caller_sheet.character.save()

        # Other user account and their character sheets
        cls.other_account = User.objects.create_user(username="capstone_other", password="testpass")
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_a.character.db_account = cls.other_account
        cls.sheet_a.character.save()

        cls.sheet_b = CharacterSheetFactory()
        cls.sheet_b.character.db_account = cls.other_account
        cls.sheet_b.character.save()

        # A third account with its own sheet (for isolation tests)
        cls.third_account = User.objects.create_user(username="capstone_third", password="testpass")
        cls.third_sheet = CharacterSheetFactory()
        cls.third_sheet.character.db_account = cls.third_account
        cls.third_sheet.character.save()

        cls.track = RelationshipTrackFactory(name="CapstoneTrack", sign=TrackSign.POSITIVE)

        # Relationship between caller and sheet_a
        cls.rel_caller_a = CharacterRelationshipFactory(source=cls.caller_sheet, target=cls.sheet_a)
        # Relationship between caller and sheet_b
        cls.rel_caller_b = CharacterRelationshipFactory(source=cls.caller_sheet, target=cls.sheet_b)
        # Relationship where caller is the TARGET (not source)
        cls.rel_a_caller = CharacterRelationshipFactory(source=cls.sheet_a, target=cls.caller_sheet)
        # Relationship belonging to a third party (no caller involvement)
        cls.rel_third_a = CharacterRelationshipFactory(source=cls.third_sheet, target=cls.sheet_a)

        # Capstone authored by caller on the caller→sheet_a relationship
        cls.capstone_caller_a = RelationshipCapstoneFactory(
            relationship=cls.rel_caller_a,
            author=cls.caller_sheet,
            track=cls.track,
            title="Caller-A Capstone",
        )
        # Capstone authored by caller on the caller→sheet_b relationship
        cls.capstone_caller_b = RelationshipCapstoneFactory(
            relationship=cls.rel_caller_b,
            author=cls.caller_sheet,
            track=cls.track,
            title="Caller-B Capstone",
        )
        # Capstone authored by sheet_a on the sheet_a→caller relationship
        cls.capstone_a_caller = RelationshipCapstoneFactory(
            relationship=cls.rel_a_caller,
            author=cls.sheet_a,
            track=cls.track,
            title="A-Caller Capstone",
        )
        # Capstone belonging entirely to a third party
        cls.capstone_third = RelationshipCapstoneFactory(
            relationship=cls.rel_third_a,
            author=cls.third_sheet,
            track=cls.track,
            title="Third Party Capstone",
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.caller_account)

    # ------------------------------------------------------------------
    # Test 1: caller isolation
    # ------------------------------------------------------------------
    def test_list_returns_callers_capstones_only(self) -> None:
        """List returns only capstones authored by the caller's character sheets."""
        response = self.client.get("/api/relationships/relationship-capstones/")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        titles = [c["title"] for c in data]
        # Caller's own capstones appear
        assert "Caller-A Capstone" in titles
        assert "Caller-B Capstone" in titles
        # Other authors' capstones do NOT appear
        assert "A-Caller Capstone" not in titles
        assert "Third Party Capstone" not in titles

    # ------------------------------------------------------------------
    # Test 2: filter by other_character_sheet_id
    # ------------------------------------------------------------------
    def test_list_filters_by_other_character_sheet_id(self) -> None:
        """Filter ?other_character_sheet_id restricts to capstones involving that sheet."""
        url = (
            f"/api/relationships/relationship-capstones/?other_character_sheet_id={self.sheet_a.pk}"
        )
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        titles = [c["title"] for c in data]
        # Only the capstone whose relationship involves sheet_a appears
        assert "Caller-A Capstone" in titles
        assert "Caller-B Capstone" not in titles

    # ------------------------------------------------------------------
    # Test 3: unauthenticated rejected
    # ------------------------------------------------------------------
    def test_unauthenticated_request_rejected(self) -> None:
        """Unauthenticated requests are rejected with 401 or 403."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/relationships/relationship-capstones/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    # ------------------------------------------------------------------
    # Test 4: detail endpoint
    # ------------------------------------------------------------------
    def test_detail_returns_one_capstone(self) -> None:
        """GET /api/relationships/relationship-capstones/{id}/ returns the capstone."""
        response = self.client.get(
            f"/api/relationships/relationship-capstones/{self.capstone_caller_a.pk}/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == self.capstone_caller_a.pk
        assert response.data["title"] == "Caller-A Capstone"
        assert response.data["author"] == self.caller_sheet.pk

    def test_detail_rejects_other_users_capstone(self) -> None:
        """Caller cannot retrieve a capstone they did not author."""
        response = self.client.get(
            f"/api/relationships/relationship-capstones/{self.capstone_third.pk}/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_results(self, response_data: dict | list) -> list:
        """Extract results from paginated or non-paginated response."""
        if isinstance(response_data, dict) and "results" in response_data:
            return response_data["results"]
        return response_data
