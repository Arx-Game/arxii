"""
Tests for Codex API views.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.codex.factories import (
    CharacterCodexKnowledgeFactory,
    CodexCategoryFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
)
from world.codex.models import CharacterCodexKnowledge
from world.roster.factories import RosterTenureFactory


class CodexAPITestCase(TestCase):
    """Base test case with codex data setup."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.account = User.objects.create_user(username="testuser", password="testpass")

        # Create category and subjects
        cls.category = CodexCategoryFactory(name="Test Category", description="Test description")
        cls.subject = CodexSubjectFactory(category=cls.category, name="Test Subject")

        # Create public entry
        cls.public_entry = CodexEntryFactory(
            subject=cls.subject,
            name="Public Entry",
            summary="Public summary",
            content="Public content",
            is_public=True,
        )

        # Create restricted entry
        cls.restricted_entry = CodexEntryFactory(
            subject=cls.subject,
            name="Restricted Entry",
            summary="Restricted summary",
            content="Secret content",
            is_public=False,
        )

        # Create user and character
        cls.tenure = RosterTenureFactory(player_data__account=cls.account)
        cls.roster_entry = cls.tenure.roster_entry

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()


class TestCodexCategoryAPI(CodexAPITestCase):
    """Tests for CodexCategoryViewSet."""

    def test_list_categories_anonymous(self):
        """Anonymous users can list categories."""
        response = self.client.get("/api/codex/categories/")
        assert response.status_code == status.HTTP_200_OK
        # Should include our test category
        names = [c["name"] for c in response.data]
        assert "Test Category" in names

    def test_retrieve_category(self):
        """Can retrieve a single category."""
        response = self.client.get(f"/api/codex/categories/{self.category.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Test Category"
        assert response.data["description"] == "Test description"

    def test_tree_endpoint(self):
        """Tree endpoint returns hierarchical structure."""
        response = self.client.get("/api/codex/categories/tree/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        # Find our test category in the response
        test_category = next((c for c in data if c["name"] == "Test Category"), None)
        assert test_category is not None
        assert len(test_category["subjects"]) >= 1


class TestCodexSubjectAPI(CodexAPITestCase):
    """Tests for CodexSubjectViewSet."""

    def test_list_subjects_anonymous(self):
        """Anonymous users can list subjects."""
        response = self.client.get("/api/codex/subjects/")
        assert response.status_code == status.HTTP_200_OK
        names = [s["name"] for s in response.data]
        assert "Test Subject" in names

    def test_retrieve_subject(self):
        """Can retrieve a single subject."""
        response = self.client.get(f"/api/codex/subjects/{self.subject.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Test Subject"

    def test_filter_subjects_by_category(self):
        """Can filter subjects by category."""
        other_category = CodexCategoryFactory(name="Other Category")
        other_subject = CodexSubjectFactory(category=other_category, name="Other Subject")

        response = self.client.get(f"/api/codex/subjects/?category={self.category.id}")
        assert response.status_code == status.HTTP_200_OK
        names = [s["name"] for s in response.data]
        assert "Test Subject" in names
        assert other_subject.name not in names


class TestCodexEntryAPI(CodexAPITestCase):
    """Tests for CodexEntryViewSet."""

    def test_list_entries_anonymous_sees_public_only(self):
        """Anonymous users see only public entries."""
        response = self.client.get("/api/codex/entries/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        names = [e["name"] for e in data]
        assert "Public Entry" in names
        assert "Restricted Entry" not in names

    def test_retrieve_public_entry_anonymous(self):
        """Anonymous users can retrieve public entry with content."""
        response = self.client.get(f"/api/codex/entries/{self.public_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["content"] == "Public content"
        assert data["summary"] == "Public summary"

    def test_retrieve_restricted_entry_anonymous_404(self):
        """Anonymous users get 404 for restricted entries."""
        response = self.client.get(f"/api/codex/entries/{self.restricted_entry.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_authenticated_without_knowledge_sees_public_only(self):
        """Authenticated user without knowledge sees only public entries."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/codex/entries/")
        data = response.data
        names = [e["name"] for e in data]
        assert "Public Entry" in names
        assert "Restricted Entry" not in names

    def test_authenticated_with_knowledge_sees_restricted(self):
        """Authenticated user with knowledge sees restricted entry."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/codex/entries/")
        data = response.data
        names = [e["name"] for e in data]
        assert "Restricted Entry" in names

    def test_uncovered_entry_visible_in_list(self):
        """UNCOVERED status allows seeing entry in list."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CharacterCodexKnowledge.Status.UNCOVERED,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/codex/entries/")
        data = response.data
        names = [e["name"] for e in data]
        assert "Restricted Entry" in names

    def test_uncovered_entry_hides_content(self):
        """UNCOVERED status shows summary but not content."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CharacterCodexKnowledge.Status.UNCOVERED,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.restricted_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["content"] is None
        assert data["summary"] == "Restricted summary"

    def test_known_entry_shows_content(self):
        """KNOWN status shows full content."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.restricted_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["content"] == "Secret content"
        assert data["summary"] == "Restricted summary"

    def test_search_endpoint(self):
        """Search returns matching entries."""
        response = self.client.get("/api/codex/entries/search/?q=Public")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data) == 1
        assert data[0]["name"] == "Public Entry"

    def test_search_respects_visibility(self):
        """Search doesn't return hidden restricted entries."""
        response = self.client.get("/api/codex/entries/search/?q=Restricted")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data) == 0

    def test_search_authenticated_with_knowledge(self):
        """Search returns restricted entries for users with knowledge."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/codex/entries/search/?q=Restricted")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data) == 1
        assert data[0]["name"] == "Restricted Entry"

    def test_search_minimum_length(self):
        """Search requires minimum query length."""
        response = self.client.get("/api/codex/entries/search/?q=P")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data) == 0  # Too short, returns empty

    def test_filter_by_subject(self):
        """Can filter entries by subject."""
        other_subject = CodexSubjectFactory(category=self.category, name="Other Subject")
        other_entry = CodexEntryFactory(subject=other_subject, name="Other Entry", is_public=True)

        response = self.client.get(f"/api/codex/entries/?subject={self.subject.id}")
        assert response.status_code == status.HTTP_200_OK
        names = [e["name"] for e in response.data]
        assert "Public Entry" in names
        assert other_entry.name not in names

    def test_filter_by_category(self):
        """Can filter entries by category."""
        other_category = CodexCategoryFactory(name="Other Category")
        other_subject = CodexSubjectFactory(category=other_category, name="Other Subject")
        other_entry = CodexEntryFactory(subject=other_subject, name="Other Entry", is_public=True)

        response = self.client.get(f"/api/codex/entries/?category={self.category.id}")
        assert response.status_code == status.HTTP_200_OK
        names = [e["name"] for e in response.data]
        assert "Public Entry" in names
        assert other_entry.name not in names

    def test_knowledge_status_in_response(self):
        """Knowledge status is included in entry response."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.public_entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.public_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["knowledge_status"] == CharacterCodexKnowledge.Status.KNOWN

    def test_research_progress_in_response(self):
        """Research progress is included for uncovered entries."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CharacterCodexKnowledge.Status.UNCOVERED,
            learning_progress=5,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.restricted_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["research_progress"] == 5
        assert data["learn_threshold"] == self.restricted_entry.learn_threshold
