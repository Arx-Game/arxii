"""ArchitecturalStyle catalog read endpoint (#1882).

Per-viewer filtered: default styles are open; throwback styles appear only
when the requesting persona's character KNOWS a codex entry under the style's
codex_subject. Mirrors the test_style_discovery.py persona/codex fixture
pattern, but tests the API endpoint rather than can_build_style directly.
"""

from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.buildings.models import ArchitecturalStyle
from world.buildings.seeds import ensure_architectural_styles
from world.character_sheets.factories import CharacterSheetFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CharacterCodexKnowledge
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory

DEFAULT_STYLE = "Vernacular Timberframe PLACEHOLDER"
THROWBACK = "Antique Imperial PLACEHOLDER"


@tag("sqlite_safe")
class ArchitecturalStyleViewSetTests(APITestCase):
    def setUp(self) -> None:
        ensure_architectural_styles()
        self.default_style = ArchitecturalStyle.objects.get(name=DEFAULT_STYLE)
        self.throwback = ArchitecturalStyle.objects.get(name=THROWBACK)

        self.account = AccountFactory()
        self.actor = CharacterFactory()
        sheet = CharacterSheetFactory(character=self.actor)
        self.roster_entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=self.roster_entry, player_data=PlayerDataFactory(account=self.account)
        )
        self.sheet = sheet

    def _get(self, url="/api/buildings/architectural-styles/", **params):
        self.client.force_authenticate(user=self.account)
        return self.client.get(url, params)

    def test_requires_authentication(self) -> None:
        response = self.client.get(
            "/api/buildings/architectural-styles/", {"character_id": self.sheet.pk}
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_missing_character_id_is_400(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/buildings/architectural-styles/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unowned_character_returns_empty(self) -> None:
        # A character_id not owned by this account: _viewer_persona returns None,
        # the queryset returns .none() — an empty result list, not a 404.
        other_sheet = CharacterSheetFactory()
        response = self._get(character_id=other_sheet.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["results"], [])

    def test_default_styles_visible_to_all(self) -> None:
        response = self._get(character_id=self.sheet.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in response.json()["results"]}
        self.assertIn(DEFAULT_STYLE, names)

    def test_throwback_hidden_until_learned(self) -> None:
        response = self._get(character_id=self.sheet.pk)
        names = {row["name"] for row in response.json()["results"]}
        self.assertNotIn(THROWBACK, names)

    def test_throwback_visible_after_learning(self) -> None:
        entry = self.throwback.codex_subject.entries.first()
        CharacterCodexKnowledge.objects.create(
            roster_entry=self.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )

        response = self._get(character_id=self.sheet.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in response.json()["results"]}
        self.assertIn(THROWBACK, names)

        throwback_row = next(row for row in response.json()["results"] if row["name"] == THROWBACK)
        self.assertFalse(throwback_row["is_default"])
        self.assertGreater(throwback_row["prestige_bonus"], 0)
        self.assertEqual(throwback_row["cost_multiplier"], "1.500")
        # The description is sourced from the linked codex_subject.
        self.assertIsNotNone(throwback_row["description"])

    def test_inactive_style_never_appears(self) -> None:
        entry = self.throwback.codex_subject.entries.first()
        CharacterCodexKnowledge.objects.create(
            roster_entry=self.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.throwback.is_active = False
        self.throwback.save(update_fields=["is_active"])

        response = self._get(character_id=self.sheet.pk)
        names = {row["name"] for row in response.json()["results"]}
        self.assertNotIn(THROWBACK, names)
