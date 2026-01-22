"""Tests for goals API views."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.goals.factories import (
    CharacterGoalFactory,
    GoalDomainFactory,
    GoalJournalFactory,
    GoalRevisionFactory,
)
from world.goals.models import CharacterGoal
from world.goals.serializers import MAX_GOAL_POINTS
from world.goals.views import CharacterContextMixin


class CharacterContextMixinTests(TestCase):
    """Tests for CharacterContextMixin header-based character retrieval."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.other_character = CharacterFactory()

    def setUp(self):
        """Set up mixin instance and mock request."""
        self.mixin = CharacterContextMixin()
        self.request = MagicMock()
        self.request.user = self.user

    def test_missing_header_returns_none(self):
        """Returns None when X-Character-ID header is missing."""
        self.request.headers = {}
        result = self.mixin._get_character(self.request)
        assert result is None

    def test_invalid_header_returns_none(self):
        """Returns None when X-Character-ID is not a valid integer."""
        self.request.headers = {"X-Character-ID": "not-a-number"}
        self.request.user.get_available_characters = MagicMock(return_value=[])
        result = self.mixin._get_character(self.request)
        assert result is None

    def test_empty_header_returns_none(self):
        """Returns None when X-Character-ID is empty string."""
        self.request.headers = {"X-Character-ID": ""}
        result = self.mixin._get_character(self.request)
        assert result is None

    def test_character_not_owned_returns_none(self):
        """Returns None when character is not in user's available characters."""
        self.request.headers = {"X-Character-ID": str(self.other_character.id)}
        # User only has access to self.character, not other_character
        self.request.user.get_available_characters = MagicMock(return_value=[self.character])
        result = self.mixin._get_character(self.request)
        assert result is None

    def test_owned_character_returned(self):
        """Returns character when ID matches an owned character."""
        self.request.headers = {"X-Character-ID": str(self.character.id)}
        self.request.user.get_available_characters = MagicMock(return_value=[self.character])
        result = self.mixin._get_character(self.request)
        assert result == self.character

    def test_multiple_characters_finds_correct_one(self):
        """Returns correct character from multiple available characters."""
        third_character = CharacterFactory()
        self.request.headers = {"X-Character-ID": str(self.other_character.id)}
        self.request.user.get_available_characters = MagicMock(
            return_value=[self.character, self.other_character, third_character]
        )
        result = self.mixin._get_character(self.request)
        assert result == self.other_character


class GoalDomainViewSetTests(TestCase):
    """Tests for GoalDomainViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = AccountFactory()
        cls.domain1 = GoalDomainFactory(
            name="TestStanding", slug="test-standing-1", display_order=1
        )
        cls.domain2 = GoalDomainFactory(name="TestWealth", slug="test-wealth-1", display_order=2)

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_domains_authenticated(self):
        """Authenticated users can list goal domains."""
        response = self.client.get("/api/goals/domains/")
        assert response.status_code == status.HTTP_200_OK
        # Should include seeded domains plus test domains
        assert len(response.data) >= 2
        slugs = [d["slug"] for d in response.data]
        assert "test-standing-1" in slugs
        assert "test-wealth-1" in slugs

    def test_list_domains_unauthenticated(self):
        """Unauthenticated users cannot list domains."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/goals/domains/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_retrieve_domain(self):
        """Can retrieve a single domain."""
        response = self.client.get(f"/api/goals/domains/{self.domain1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "TestStanding"
        assert response.data["slug"] == "test-standing-1"


class CharacterGoalViewSetTests(TestCase):
    """Tests for CharacterGoalViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.standing = GoalDomainFactory(slug="test-standing-cg")
        cls.wealth = GoalDomainFactory(slug="test-wealth-cg")
        cls.knowledge = GoalDomainFactory(slug="test-knowledge-cg")

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("world.goals.views.CharacterGoalViewSet._get_character")
    def test_list_goals_with_character(self, mock_get_char):
        """Can list character's goals."""
        mock_get_char.return_value = self.character
        CharacterGoalFactory(
            character=self.character,
            domain=self.standing,
            points=15,
        )
        response = self.client.get("/api/goals/my-goals/")

        assert response.status_code == status.HTTP_200_OK
        assert "goals" in response.data
        assert "total_points" in response.data
        assert "points_remaining" in response.data
        assert "revision" in response.data
        assert response.data["total_points"] == 15
        assert response.data["points_remaining"] == MAX_GOAL_POINTS - 15

    @patch("world.goals.views.CharacterGoalViewSet._get_character")
    def test_list_goals_no_character(self, mock_get_char):
        """Returns 404 when user has no character."""
        mock_get_char.return_value = None
        response = self.client.get("/api/goals/my-goals/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "No character found" in response.data["detail"]

    @patch("world.goals.views.CharacterGoalViewSet._get_character")
    def test_update_all_creates_goals(self, mock_get_char):
        """update_all action creates new goals."""
        mock_get_char.return_value = self.character
        data = {
            "goals": [
                {"domain_slug": "test-standing-cg", "points": 15, "notes": "Become Count"},
                {"domain_slug": "test-wealth-cg", "points": 10},
            ]
        }
        response = self.client.post(
            "/api/goals/my-goals/update/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, (
            f"Got {response.status_code}: {response.data}"
        )
        assert response.data["total_points"] == 25
        assert response.data["points_remaining"] == 5

        # Verify goals were created
        goals = CharacterGoal.objects.filter(character=self.character)
        assert goals.count() == 2

    @patch("world.goals.views.CharacterGoalViewSet._get_character")
    def test_update_all_replaces_existing_goals(self, mock_get_char):
        """update_all replaces existing goals."""
        mock_get_char.return_value = self.character
        # Create existing goal
        CharacterGoalFactory(
            character=self.character,
            domain=self.standing,
            points=20,
        )
        # Create revision allowing changes
        revision = GoalRevisionFactory(character=self.character)
        revision.last_revised_at = timezone.now() - timedelta(weeks=2)
        revision.save()

        data = {
            "goals": [
                {"domain_slug": "test-wealth-cg", "points": 10},
            ]
        }
        response = self.client.post(
            "/api/goals/my-goals/update/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        goals = CharacterGoal.objects.filter(character=self.character)
        assert goals.count() == 1
        assert goals.first().domain.slug == "test-wealth-cg"

    @patch("world.goals.views.CharacterGoalViewSet._get_character")
    def test_update_all_respects_revision_limit(self, mock_get_char):
        """update_all enforces weekly revision limit."""
        mock_get_char.return_value = self.character
        # Create existing goal
        CharacterGoalFactory(character=self.character, domain=self.standing, points=10)
        # Create recent revision
        GoalRevisionFactory(character=self.character)

        data = {
            "goals": [
                {"domain_slug": "test-wealth-cg", "points": 10},
            ]
        }
        response = self.client.post(
            "/api/goals/my-goals/update/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot revise goals yet" in response.data["detail"]
        assert "next_revision_at" in response.data

    @patch("world.goals.views.CharacterGoalViewSet._get_character")
    def test_update_all_allows_first_time_setup(self, mock_get_char):
        """update_all allows setting goals for first time without revision check."""
        mock_get_char.return_value = self.character
        data = {
            "goals": [
                {"domain_slug": "test-standing-cg", "points": 30},
            ]
        }
        response = self.client.post(
            "/api/goals/my-goals/update/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

    @patch("world.goals.views.CharacterGoalViewSet._get_character")
    def test_update_all_validates_points(self, mock_get_char):
        """update_all validates point total."""
        mock_get_char.return_value = self.character
        data = {
            "goals": [
                {"domain_slug": "test-standing-cg", "points": 25},
                {"domain_slug": "test-wealth-cg", "points": 25},
            ]
        }
        response = self.client.post(
            "/api/goals/my-goals/update/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_access_denied(self):
        """Unauthenticated users cannot access character goals."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/goals/my-goals/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class GoalJournalViewSetTests(TestCase):
    """Tests for GoalJournalViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = AccountFactory()
        cls.other_user = AccountFactory()
        cls.character = CharacterFactory()
        cls.other_character = CharacterFactory()
        cls.domain = GoalDomainFactory(slug="test-journal-domain")

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("world.goals.views.GoalJournalViewSet._get_character")
    def test_list_journals(self, mock_get_char):
        """Can list character's journal entries."""
        mock_get_char.return_value = self.character
        GoalJournalFactory(character=self.character, title="My Journal")
        GoalJournalFactory(character=self.other_character, title="Other Journal")

        response = self.client.get("/api/goals/journals/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["title"] == "My Journal"

    @patch("world.goals.views.GoalJournalViewSet._get_character")
    def test_create_journal(self, mock_get_char):
        """Can create a new journal entry."""
        mock_get_char.return_value = self.character
        data = {
            "domain_slug": "test-journal-domain",
            "title": "New Entry",
            "content": "Today I made progress...",
            "is_public": False,
        }
        response = self.client.post(
            "/api/goals/journals/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "New Entry"
        assert response.data["xp_awarded"] == 1

    @patch("world.goals.views.GoalJournalViewSet._get_character")
    def test_create_journal_without_domain(self, mock_get_char):
        """Can create journal without specifying domain."""
        mock_get_char.return_value = self.character
        data = {
            "title": "General Thoughts",
            "content": "Some reflections",
        }
        response = self.client.post(
            "/api/goals/journals/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["domain"] is None

    def test_public_journals_endpoint(self):
        """Public endpoint returns only public journals."""
        GoalJournalFactory(character=self.character, is_public=True, title="Public")
        GoalJournalFactory(character=self.character, is_public=False, title="Private")
        GoalJournalFactory(character=self.other_character, is_public=True, title="Other Public")

        response = self.client.get("/api/goals/journals/public/")

        assert response.status_code == status.HTTP_200_OK
        # Paginated response
        results = response.data.get("results", response.data)
        titles = [j["title"] for j in results]
        assert "Public" in titles
        assert "Other Public" in titles
        assert "Private" not in titles

    def test_public_journals_filter_by_character(self):
        """Public endpoint can filter by character_id."""
        GoalJournalFactory(character=self.character, is_public=True, title="Mine")
        GoalJournalFactory(character=self.other_character, is_public=True, title="Theirs")

        response = self.client.get(f"/api/goals/journals/public/?character_id={self.character.id}")

        assert response.status_code == status.HTTP_200_OK
        # Paginated response
        results = response.data.get("results", response.data)
        assert len(results) == 1
        assert results[0]["title"] == "Mine"

    @patch("world.goals.views.GoalJournalViewSet._get_character")
    def test_list_journals_no_character(self, mock_get_char):
        """Returns 404 when user has no character."""
        mock_get_char.return_value = None
        response = self.client.get("/api/goals/journals/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_access_denied(self):
        """Unauthenticated users cannot access journals."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/goals/journals/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
