"""Tests for GET /api/progression/path-options/ (#954)."""

from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.progression.factories import CharacterPathHistoryFactory

URL = "/api/progression/path-options/"


class PathOptionsTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.prospect = PathFactory(name="Steel Prospect", stage=PathStage.PROSPECT)
        self.child_a = PathFactory(name="Potential A", stage=PathStage.POTENTIAL)
        self.child_b = PathFactory(name="Potential B", stage=PathStage.POTENTIAL)
        for child in (self.child_a, self.child_b):
            child.parent_paths.add(self.prospect)
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)  # type: ignore[arg-type]

    @patch("world.progression.views.PathOptionsView._get_character")
    def test_returns_current_path_and_options(self, mock_char: object) -> None:
        mock_char.return_value = self.character
        CharacterPathHistoryFactory(character=self.sheet, path=self.prospect)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_path"]["name"] == "Steel Prospect"
        names = {p["name"] for p in response.data["options"]}
        assert names == {"Potential A", "Potential B"}

    @patch("world.progression.views.PathOptionsView._get_character")
    def test_terminal_path_returns_empty_options(self, mock_char: object) -> None:
        mock_char.return_value = self.character
        CharacterPathHistoryFactory(character=self.sheet, path=self.child_a)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_path"]["name"] == "Potential A"
        assert response.data["options"] == []

    @patch("world.progression.views.PathOptionsView._get_character")
    def test_no_history_returns_null_current_path(self, mock_char: object) -> None:
        mock_char.return_value = self.character
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_path"] is None
        assert response.data["options"] == []

    @patch("world.progression.views.PathOptionsView._get_character")
    def test_no_character_returns_404(self, mock_char: object) -> None:
        mock_char.return_value = None
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_returns_403(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
