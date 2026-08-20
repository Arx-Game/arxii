"""Shop-window perspective endpoints for the CG wizard (#3281, ADR-0224)."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory


class BeginningsPerspectivesEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.character_creation.factories import BeginningsFactory
        from world.codex.factories import (
            BeginningsCodexGrantFactory,
            CodexEntryFactory,
            CodexSubjectFactory,
        )

        cls.account = AccountFactory()
        cls.beginnings = BeginningsFactory()
        subject = CodexSubjectFactory(name="The Duskborn")
        cls.opinion = CodexEntryFactory(
            subject=subject,
            name="Duskborn Doorways",
            summary="They talk to doors.",
            lore_content="Every Duskborn home has a second door no guest may use.",
            is_public=False,
        )
        BeginningsCodexGrantFactory(
            beginnings=cls.beginnings, entry=cls.opinion, is_perspective=True
        )
        # A plain (non-perspective) grant that must NOT appear
        cls.plain = CodexEntryFactory(subject=subject, is_public=False)
        BeginningsCodexGrantFactory(beginnings=cls.beginnings, entry=cls.plain)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_returns_only_flagged_grants_with_subject_names(self):
        response = self.client.get(
            f"/api/character-creation/beginnings/{self.beginnings.id}/perspectives/"
        )
        assert response.status_code == 200
        data = response.json()
        assert [row["entry_id"] for row in data] == [self.opinion.id]
        row = data[0]
        assert row["name"] == "Duskborn Doorways"
        assert row["summary"] == "They talk to doors."
        assert row["lore_content"].startswith("Every Duskborn home")
        assert row["subject_name"] == "The Duskborn"

    def test_anonymous_gets_401_or_403(self):
        self.client.logout()
        response = self.client.get(
            f"/api/character-creation/beginnings/{self.beginnings.id}/perspectives/"
        )
        assert response.status_code in (401, 403)

    def test_codex_proper_still_gates_the_entry(self):
        """The carve-out must not widen codex visibility (regression pin)."""
        response = self.client.get(f"/api/codex/entries/{self.opinion.id}/")
        assert response.status_code == 404


class TraditionPerspectivesEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.codex.factories import (
            CodexEntryFactory,
            CodexSubjectFactory,
            TraditionCodexGrantFactory,
        )
        from world.magic.factories import TraditionFactory

        cls.account = AccountFactory()
        cls.tradition = TraditionFactory(is_active=True)
        subject_a = CodexSubjectFactory(name="A Silent Choir")
        subject_b = CodexSubjectFactory(name="B Wandering Vow")
        cls.opinion_a = CodexEntryFactory(subject=subject_a, is_public=False)
        cls.opinion_b = CodexEntryFactory(subject=subject_b, is_public=False)
        # Grants created out of subject-name order, to pin the order_by clause.
        TraditionCodexGrantFactory(
            tradition=cls.tradition, entry=cls.opinion_b, is_perspective=True
        )
        TraditionCodexGrantFactory(
            tradition=cls.tradition, entry=cls.opinion_a, is_perspective=True
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_returns_flagged_grants_without_beginning_id_param(self):
        response = self.client.get(
            f"/api/character-creation/traditions/{self.tradition.id}/perspectives/"
        )
        assert response.status_code == 200
        assert [row["entry_id"] for row in response.json()] == [
            self.opinion_a.id,
            self.opinion_b.id,
        ]

    def test_inactive_tradition_404s(self):
        from world.magic.factories import TraditionFactory

        inactive = TraditionFactory(is_active=False)
        response = self.client.get(
            f"/api/character-creation/traditions/{inactive.id}/perspectives/"
        )
        assert response.status_code == 404
