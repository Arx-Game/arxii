"""Tests for codex container hiding and account-wide knowledge union.

Categories and subjects are pure taxonomy: their names and descriptions have
no visibility of their own, so any container whose subtree holds no visible
entry must be hidden everywhere (tree, list, retrieve, children) -- otherwise
the subject description becomes the canonical public prose for a topic no
entry supports, and an all-secret branch leaks its existence.

Knowledge is account-wide: a player sees the union of what all their
characters know, optionally narrowed with ``?character=<roster_entry_id>``.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import (
    CharacterCodexKnowledgeFactory,
    CodexCategoryFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
)
from world.roster.factories import RosterTenureFactory


class ContainerVisibilityTestCase(TestCase):
    """Shared fixture: one populated branch, one empty branch, one secret branch."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="viewer")
        cls.tenure = RosterTenureFactory(player_data__account=cls.account)
        cls.roster_entry = cls.tenure.roster_entry

        # Category with a public entry under a nested subject: every ancestor
        # visible, sibling empty subject hidden.
        cls.populated_category = CodexCategoryFactory(name="Populated Category")
        cls.populated_parent = CodexSubjectFactory(
            category=cls.populated_category, name="Populated Parent"
        )
        cls.populated_child = CodexSubjectFactory(
            category=cls.populated_category,
            parent=cls.populated_parent,
            name="Populated Child",
        )
        cls.public_entry = CodexEntryFactory(
            subject=cls.populated_child, name="Deep Public Entry", is_public=True
        )
        cls.empty_sibling = CodexSubjectFactory(
            category=cls.populated_category, name="Empty Sibling"
        )

        # Category whose only entry is secret: invisible to anonymous,
        # visible to the character who knows the entry.
        cls.secret_category = CodexCategoryFactory(name="Secret Category")
        cls.secret_subject = CodexSubjectFactory(
            category=cls.secret_category, name="Secret Subject"
        )
        cls.secret_entry = CodexEntryFactory(
            subject=cls.secret_subject, name="Secret Entry", is_public=False
        )

        # Category with no entries at all.
        cls.empty_category = CodexCategoryFactory(name="Empty Category")
        CodexSubjectFactory(category=cls.empty_category, name="Empty Subject")

    def setUp(self):
        self.client = APIClient()

    def _tree(self):
        response = self.client.get("/api/codex/categories/tree/")
        assert response.status_code == status.HTTP_200_OK
        return {category["name"]: category for category in response.data}


class TestAnonymousContainerHiding(ContainerVisibilityTestCase):
    """Anonymous visitors never see a container with no visible entries."""

    def test_tree_hides_empty_subjects_and_categories(self):
        tree = self._tree()
        assert "Populated Category" in tree
        assert "Secret Category" not in tree
        assert "Empty Category" not in tree
        subject_names = [s["name"] for s in tree["Populated Category"]["subjects"]]
        assert "Populated Parent" in subject_names
        assert "Empty Sibling" not in subject_names

    def test_tree_ancestor_of_deep_entry_visible_with_children_flag(self):
        tree = self._tree()
        parent = next(
            s for s in tree["Populated Category"]["subjects"] if s["name"] == "Populated Parent"
        )
        # Direct entry count is zero (the entry lives on the child), but the
        # subject stays visible and expandable because a descendant has one.
        assert parent["entry_count"] == 0
        assert parent["has_children"] is True

    def test_children_endpoint_filters_hidden_children(self):
        response = self.client.get(f"/api/codex/subjects/{self.populated_parent.id}/children/")
        assert response.status_code == status.HTTP_200_OK
        names = [child["name"] for child in response.data]
        assert names == ["Populated Child"]

    def test_subject_list_excludes_hidden(self):
        response = self.client.get("/api/codex/subjects/")
        assert response.status_code == status.HTTP_200_OK
        names = [subject["name"] for subject in response.data]
        assert "Populated Parent" in names
        assert "Empty Sibling" not in names
        assert "Secret Subject" not in names

    def test_hidden_subject_retrieve_404s(self):
        response = self.client.get(f"/api/codex/subjects/{self.secret_subject.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_hidden_category_retrieve_404s(self):
        response = self.client.get(f"/api/codex/categories/{self.secret_category.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_category_list_excludes_hidden(self):
        response = self.client.get("/api/codex/categories/")
        assert response.status_code == status.HTTP_200_OK
        names = [category["name"] for category in response.data]
        assert "Populated Category" in names
        assert "Secret Category" not in names


class TestKnowledgeRevealsContainers(ContainerVisibilityTestCase):
    """A known secret entry reveals its whole ancestor chain to its knower."""

    def test_secret_branch_visible_to_knowing_character(self):
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.secret_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        tree = self._tree()
        assert "Secret Category" in tree
        subject_names = [s["name"] for s in tree["Secret Category"]["subjects"]]
        assert "Secret Subject" in subject_names

    def test_secret_branch_stays_hidden_without_knowledge(self):
        self.client.force_authenticate(user=self.account)
        tree = self._tree()
        assert "Secret Category" not in tree


class TestAccountKnowledgeUnion(ContainerVisibilityTestCase):
    """Knowledge is the union across the account's characters, with known_by."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Second character on the same account.
        cls.tenure_b = RosterTenureFactory(player_data=cls.tenure.player_data)
        cls.roster_entry_b = cls.tenure_b.roster_entry
        cls.knowledge_a = CharacterCodexKnowledgeFactory(
            roster_entry=cls.roster_entry,
            entry=cls.secret_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )

    def _entry_detail(self, entry_id, params=""):
        return self.client.get(f"/api/codex/entries/{entry_id}/{params}")

    def test_union_shows_entry_known_by_any_character(self):
        self.client.force_authenticate(user=self.account)
        response = self._entry_detail(self.secret_entry.id)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["knowledge_status"] == CodexKnowledgeStatus.KNOWN
        assert response.data["lore_content"] is not None

    def test_known_by_lists_each_knowing_character(self):
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry_b,
            entry=self.secret_entry,
            status=CodexKnowledgeStatus.UNCOVERED,
            learning_progress=3,
        )
        self.client.force_authenticate(user=self.account)
        response = self._entry_detail(self.secret_entry.id)
        assert response.status_code == status.HTTP_200_OK
        known_by = response.data["known_by"]
        assert len(known_by) == 2
        by_id = {row["roster_entry_id"]: row for row in known_by}
        name_a = self.roster_entry.character_sheet.character.name
        name_b = self.roster_entry_b.character_sheet.character.name
        assert by_id[self.roster_entry.id]["character_name"] == name_a
        assert by_id[self.roster_entry.id]["status"] == CodexKnowledgeStatus.KNOWN
        assert by_id[self.roster_entry_b.id]["character_name"] == name_b
        assert by_id[self.roster_entry_b.id]["status"] == CodexKnowledgeStatus.UNCOVERED
        assert by_id[self.roster_entry_b.id]["research_progress"] == 3
        # Aggregates take the best status and the furthest progress.
        assert response.data["knowledge_status"] == CodexKnowledgeStatus.KNOWN

    def test_character_param_narrows_to_one_character(self):
        self.client.force_authenticate(user=self.account)
        response = self._entry_detail(self.secret_entry.id, f"?character={self.roster_entry_b.id}")
        # Character B knows nothing: the secret entry is not visible at all.
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_character_param_scopes_known_by(self):
        self.client.force_authenticate(user=self.account)
        response = self._entry_detail(self.secret_entry.id, f"?character={self.roster_entry.id}")
        assert response.status_code == status.HTTP_200_OK
        known_by = response.data["known_by"]
        assert [row["roster_entry_id"] for row in known_by] == [self.roster_entry.id]

    def test_foreign_character_param_yields_public_only(self):
        other_account = AccountFactory(username="other")
        other_tenure = RosterTenureFactory(player_data__account=other_account)
        CharacterCodexKnowledgeFactory(
            roster_entry=other_tenure.roster_entry,
            entry=self.secret_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.client.force_authenticate(user=self.account)
        response = self._entry_detail(
            self.secret_entry.id, f"?character={other_tenure.roster_entry.id}"
        )
        # Another player's roster entry id never widens visibility.
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_entry_list_carries_known_by(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/codex/entries/")
        assert response.status_code == status.HTTP_200_OK
        by_name = {row["name"]: row for row in response.data}
        assert by_name["Secret Entry"]["known_by"][0]["status"] == CodexKnowledgeStatus.KNOWN
        assert by_name["Deep Public Entry"]["known_by"] == []
