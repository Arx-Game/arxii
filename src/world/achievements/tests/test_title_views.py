"""API tests for GET /api/achievements/character-titles/ (#1522).

A character's earned titles are cosmetic and public — any authenticated user can read any
character's titles, filtered by ``character_sheet``.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.achievements.factories import RewardDefinitionFactory
from world.achievements.models import CharacterTitle
from world.character_sheets.factories import CharacterSheetFactory

TITLES_URL = "/api/achievements/character-titles/"


class CharacterTitleApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.reward = RewardDefinitionFactory(name="Hot Flex But Okay")

    def test_requires_authentication(self) -> None:
        response = self.client.get(TITLES_URL, {"character_sheet": self.sheet.pk})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_lists_a_characters_titles(self) -> None:
        CharacterTitle.objects.create(character_sheet=self.sheet, reward=self.reward)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"character_sheet": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(rows) == 1
        assert rows[0]["title"] == "Hot Flex But Okay"
        assert rows[0]["reward_key"] == self.reward.key

    def test_filters_by_character_sheet(self) -> None:
        CharacterTitle.objects.create(character_sheet=self.sheet, reward=self.reward)
        other_reward = RewardDefinitionFactory(name="Other Title")
        CharacterTitle.objects.create(character_sheet=self.other_sheet, reward=other_reward)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"character_sheet": self.other_sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(rows) == 1
        assert rows[0]["title"] == "Other Title"

    def test_empty_when_no_titles(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"character_sheet": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert rows == []
