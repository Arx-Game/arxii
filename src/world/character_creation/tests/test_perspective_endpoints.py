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
