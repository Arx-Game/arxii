"""Board postings + take API (#2044).

Player-scoped (IsAuthenticated). The board is keyed by its ObjectDB pk —
the same object the player examines in-world.
"""

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
from world.missions.constants import GiverKind, MissionVisibility
from world.missions.factories import (
    MissionGiverFactory,
    MissionNodeFactory,
    MissionTemplateFactory,
)


def _template_with_entry(name: str) -> object:
    template = MissionTemplateFactory(name=name)
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class _BoardAPIMixin(TestCase):
    """Shared setup for board API tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        CharacterSheetFactory(character=cls.character)
        cls.board_obj = ObjectDBFactory()  # plain Object typeclass
        cls.template_open = _template_with_entry("board-api-open")
        cls.account = AccountFactory()

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        self._patch = mock.patch(
            "world.missions.views._puppet_character", return_value=self.character
        )
        self._patch.start()
        self.addCleanup(self._patch.stop)


class BoardPostingsAPITests(_BoardAPIMixin):
    """GET /api/missions/boards/<pk>/postings/ — viewer-scoped postings."""

    def test_list_postings(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        giver.templates.add(self.template_open)
        resp = self.client.get(f"/api/missions/boards/{self.board_obj.pk}/postings/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["template_id"], self.template_open.pk)

    def test_404_when_not_a_board(self) -> None:
        resp = self.client.get(f"/api/missions/boards/{self.board_obj.pk}/postings/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class BoardTakeAPITests(_BoardAPIMixin):
    """POST /api/missions/boards/<pk>/take/ — accept a posting."""

    def test_take_eligible_posting(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        giver.templates.add(self.template_open)
        resp = self.client.post(
            f"/api/missions/boards/{self.board_obj.pk}/take/",
            {"template_id": self.template_open.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["template_id"], self.template_open.pk)

    def test_take_rejected_ineligible(self) -> None:
        restricted = _template_with_entry("board-api-restricted")
        restricted.visibility = MissionVisibility.RESTRICTED
        restricted.save(update_fields=["visibility"])
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        giver.templates.add(restricted)
        resp = self.client.post(
            f"/api/missions/boards/{self.board_obj.pk}/take/",
            {"template_id": restricted.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
