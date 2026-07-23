"""
Tests for Codex API views.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import (
    CharacterCodexKnowledgeFactory,
    CodexCategoryFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
)
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
            lore_content="Public lore content",
            mechanics_content="Public mechanics content",
            is_public=True,
        )

        # Create featured public entry
        cls.featured_entry = CodexEntryFactory(
            subject=cls.subject,
            name="Featured Entry",
            summary="Featured summary",
            lore_content="Featured lore content",
            mechanics_content="Featured mechanics content",
            is_public=True,
            is_featured=True,
            featured_order=1,
        )

        # Create restricted entry
        cls.restricted_entry = CodexEntryFactory(
            subject=cls.subject,
            name="Restricted Entry",
            summary="Restricted summary",
            lore_content="Secret lore content",
            mechanics_content="Secret mechanics content",
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

    def test_featured_filter_returns_only_featured_public(self):
        """?featured=true returns only featured public entries, ordered by featured_order."""
        response = self.client.get("/api/codex/entries/?featured=true")
        assert response.status_code == status.HTTP_200_OK
        names = [e["name"] for e in response.data]
        assert "Featured Entry" in names
        assert "Public Entry" not in names  # public but not featured

    def test_featured_field_in_list_serializer(self):
        """List serializer includes is_featured and featured_order."""
        response = self.client.get("/api/codex/entries/")
        featured = next(e for e in response.data if e["name"] == "Featured Entry")
        assert featured["is_featured"] is True
        assert featured["featured_order"] == 1

    def test_retrieve_public_entry_anonymous(self):
        """Anonymous users can retrieve public entry with content."""
        response = self.client.get(f"/api/codex/entries/{self.public_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["lore_content"] == "Public lore content"
        assert data["mechanics_content"] == "Public mechanics content"
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
            status=CodexKnowledgeStatus.KNOWN,
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
            status=CodexKnowledgeStatus.UNCOVERED,
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
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.restricted_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["lore_content"] is None
        assert data["mechanics_content"] is None
        assert data["summary"] == "Restricted summary"

    def test_known_entry_shows_content(self):
        """KNOWN status shows full content."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.restricted_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["lore_content"] == "Secret lore content"
        assert data["mechanics_content"] == "Secret mechanics content"
        assert data["summary"] == "Restricted summary"

    def test_search_filter(self):
        """Search filter returns matching entries."""
        response = self.client.get("/api/codex/entries/?search=Public")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data) == 1
        assert data[0]["name"] == "Public Entry"

    def test_search_filter_respects_visibility(self):
        """Search filter doesn't return hidden restricted entries."""
        response = self.client.get("/api/codex/entries/?search=Restricted")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data) == 0

    def test_search_filter_authenticated_with_knowledge(self):
        """Search filter returns restricted entries for users with knowledge."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/codex/entries/?search=Restricted")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data) == 1
        assert data[0]["name"] == "Restricted Entry"

    def test_search_filter_minimum_length(self):
        """Search filter requires minimum query length."""
        response = self.client.get("/api/codex/entries/?search=P")
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
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.public_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["knowledge_status"] == CodexKnowledgeStatus.KNOWN

    def test_research_progress_in_response(self):
        """Research progress is included for uncovered entries."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CodexKnowledgeStatus.UNCOVERED,
            learning_progress=5,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{self.restricted_entry.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["research_progress"] == 5
        assert data["learn_threshold"] == self.restricted_entry.learn_threshold

    def test_lore_links_in_response_for_public_entry(self):
        """lore_links field is present and resolved for public entries."""
        linked_entry = CodexEntryFactory(
            subject=self.subject,
            name="Linked Public Entry",
            lore_content="Linked lore",
            is_public=True,
        )
        entry_with_link = CodexEntryFactory(
            subject=self.subject,
            name="Entry With Link",
            lore_content="See [[Linked Public Entry]] for details.",
            is_public=True,
        )
        response = self.client.get(f"/api/codex/entries/{entry_with_link.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert "lore_links" in data
        assert "mechanics_links" in data
        assert len(data["lore_links"]) == 1
        assert data["lore_links"][0]["entry_id"] == linked_entry.id
        assert data["lore_links"][0]["accessible"] is True

    def test_links_empty_when_content_gated(self):
        """lore_links is empty list when content is not visible."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        # Create a new restricted entry with a link (can't .save() existing
        # entries due to the breadcrumb REFRESH MATERIALIZED VIEW on SQLite)
        entry_with_link = CodexEntryFactory(
            subject=self.subject,
            name="Gated Entry With Link",
            lore_content="See [[Public Entry]].",
            is_public=False,
        )
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=entry_with_link,
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(f"/api/codex/entries/{entry_with_link.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["lore_content"] is None
        assert data["lore_links"] == []

    def test_inaccessible_link_does_not_leak_name(self):
        """Inaccessible link in content returns ??? and no entry_id."""
        # Public entry links to a restricted entry the reader can't see
        entry_with_link = CodexEntryFactory(
            subject=self.subject,
            name="Entry With Inaccessible Link",
            lore_content="See [[Restricted Entry]] if you dare.",
            is_public=True,
        )
        response = self.client.get(f"/api/codex/entries/{entry_with_link.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert len(data["lore_links"]) == 1
        link = data["lore_links"][0]
        assert link["entry_id"] is None
        assert link["display_text"] == "???"
        assert link["accessible"] is False
        # The real entry name must not appear
        assert "Restricted Entry" not in link["display_text"]


class TestCodexTreeQueryCount(TestCase):
    """Lock the query count on the codex tree endpoint.

    Regression guard for the previous N+1 in
    ``CodexSubjectTreeSerializer.get_entry_count`` — a
    ``filter(...).count()`` per subject. With the queryset annotation,
    the count is folded into the subjects prefetch and grows O(1) in the
    number of subjects (not O(N)).
    """

    @classmethod
    def setUpTestData(cls):
        # Two categories with several top-level subjects each. Each subject
        # has a mix of public and (for some) restricted entries.
        cls.category_a = CodexCategoryFactory(name="QC Cat A")
        cls.category_b = CodexCategoryFactory(name="QC Cat B")

        cls.subjects = []
        for category in (cls.category_a, cls.category_b):
            for index in range(4):  # 8 subjects total
                subject = CodexSubjectFactory(
                    category=category, name=f"QC {category.name} Subject {index}"
                )
                cls.subjects.append(subject)
                # Two public entries per subject so entry_count > 0.
                for entry_index in range(2):
                    CodexEntryFactory(
                        subject=subject,
                        name=f"{subject.name} entry {entry_index}",
                        is_public=True,
                    )
                # One restricted entry that anonymous users won't count.
                CodexEntryFactory(
                    subject=subject,
                    name=f"{subject.name} restricted",
                    is_public=False,
                )

    def setUp(self):
        self.client = APIClient()

    def _count_relevant(self, response_data):
        """Return {subject_name: entry_count} for our QC-prefixed test rows."""
        subjects = [subject for category in response_data for subject in category["subjects"]]
        return {s["name"]: s["entry_count"] for s in subjects if s["name"].startswith("QC ")}

    def test_anonymous_tree_query_count_constant_with_subjects(self):
        """Anonymous tree fetch is O(1) in subject count, not O(N)."""
        # Warmup: prime any per-process caches (content type lookups, etc.)
        # so the assertNumQueries below sees only the steady-state queries.
        warmup = self.client.get("/api/codex/categories/tree/")
        assert warmup.status_code == status.HTTP_200_OK

        # Steady-state queries for the anonymous tree endpoint:
        #   1. SELECT django_session
        #   2. SELECT public CodexEntry ids (visibility set)
        #   3. SELECT top-level CodexSubjects (with has_children + entry_count)
        #   4. SELECT CodexCategory list
        # The prior N+1 added one COUNT per subject (8 here) -> 12 queries.
        # After the fix the count is constant in the number of subjects.
        with self.assertNumQueries(4):
            response = self.client.get("/api/codex/categories/tree/")
        assert response.status_code == status.HTTP_200_OK

        # Sanity check: entry_count is populated from the annotation and
        # only counts visible (public) entries — 2 per subject for anon.
        relevant = self._count_relevant(response.data)
        assert len(relevant) == 8
        for value in relevant.values():
            assert value == 2

    def test_authenticated_tree_query_count_constant_with_subjects(self):
        """Authenticated tree fetch is O(1) in subject count, not O(N)."""
        User = get_user_model()
        account = User.objects.create_user(username="qcuser", password="qcpass")
        tenure = RosterTenureFactory(player_data__account=account)
        # Mark one restricted entry as known so the visibility set differs
        # from the public-only set (exercises the union path).
        restricted = self.subjects[0].entries.filter(is_public=False).first()
        CharacterCodexKnowledgeFactory(
            roster_entry=tenure.roster_entry,
            entry=restricted,
            status=CodexKnowledgeStatus.KNOWN,
        )

        self.client.force_authenticate(user=account)
        warmup = self.client.get("/api/codex/categories/tree/")
        assert warmup.status_code == status.HTTP_200_OK

        # Steady-state queries for the authenticated tree endpoint:
        #   1. SELECT django_session
        #   2. SELECT public CodexEntry ids
        #   3. Resolve active RosterEntry (tenures join)
        #   4. SELECT known CharacterCodexKnowledge entry_ids for that entry
        #   5. SELECT top-level CodexSubjects (with has_children + entry_count)
        #   6. SELECT CodexCategory list
        # Prior to the fix this also fired one COUNT per subject.
        with self.assertNumQueries(6):
            response = self.client.get("/api/codex/categories/tree/")
        assert response.status_code == status.HTTP_200_OK

        # The subject whose restricted entry is now visible should report
        # 3; all other subjects should still report 2.
        relevant = self._count_relevant(response.data)
        assert relevant[self.subjects[0].name] == 3
        for subject in self.subjects[1:]:
            assert relevant[subject.name] == 2
