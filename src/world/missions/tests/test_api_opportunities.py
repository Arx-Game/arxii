"""Opportunities API endpoint (#2044)."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.factories import (
    MissionNodeFactory,
    MissionTemplateFactory,
)


def _template_with_entry(name: str) -> object:
    template = MissionTemplateFactory(name=name)
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class OpportunitiesAPITests(TestCase):
    """GET /api/missions/journal/opportunities/ — the three groups."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        cls.character = CharacterFactory()
        CharacterSheetFactory(character=cls.character)
        cls.character.db_location = cls.room
        cls.character.save(update_fields=["db_location"])
        cls.template_open = _template_with_entry("opp-api-open")
        cls.account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        self._patch = mock.patch(
            "world.missions.views._puppet_character", return_value=self.character
        )
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_returns_three_groups(self) -> None:
        resp = self.client.get("/api/missions/journal/opportunities/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("here", data)
        self.assertIn("nearby", data)
        self.assertIn("your_organizations", data)

    def test_empty_when_no_givers(self) -> None:
        resp = self.client.get("/api/missions/journal/opportunities/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["here"], [])
        self.assertEqual(data["nearby"], [])
        self.assertEqual(data["your_organizations"], [])
