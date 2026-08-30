"""API tests for GET /api/achievements/character-titles/ (#1522, #3466).

A persona's earned titles are cosmetic and public — any authenticated user can read any
persona's titles, filtered by ``persona``. Deliberately NOT filterable by character sheet:
that would traverse from a sheet to all of its personas, including masks (#3466).
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.achievements.factories import RewardDefinitionFactory
from world.achievements.models import PersonaTitle
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.factories import LegendEntryFactory

TITLES_URL = "/api/achievements/character-titles/"


class CharacterTitleApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.reward = RewardDefinitionFactory(name="Hot Flex But Okay")

    def test_requires_authentication(self) -> None:
        response = self.client.get(TITLES_URL, {"persona": self.sheet.primary_persona.pk})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_lists_a_personas_titles(self) -> None:
        PersonaTitle.objects.create(persona=self.sheet.primary_persona, reward=self.reward)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"persona": self.sheet.primary_persona.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(rows) == 1
        assert rows[0]["title"] == "Hot Flex But Okay"
        assert rows[0]["reward_key"] == self.reward.key

    def test_filters_by_persona(self) -> None:
        PersonaTitle.objects.create(persona=self.sheet.primary_persona, reward=self.reward)
        other_reward = RewardDefinitionFactory(name="Other Title")
        PersonaTitle.objects.create(persona=self.other_sheet.primary_persona, reward=other_reward)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"persona": self.other_sheet.primary_persona.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(rows) == 1
        assert rows[0]["title"] == "Other Title"

    def test_empty_when_no_titles(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"persona": self.sheet.primary_persona.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert rows == []

    def test_deed_branch_serializes_with_display_name_and_null_reward_key(self) -> None:
        deed = LegendEntryFactory(persona=self.sheet.primary_persona, title="Slew the Wyrm")
        PersonaTitle.objects.create(persona=self.sheet.primary_persona, legend_entry=deed)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"persona": self.sheet.primary_persona.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(rows) == 1
        assert rows[0]["title"] == "Slew the Wyrm"
        assert rows[0]["reward_key"] is None

    def test_a_masked_personas_title_is_not_reachable_via_the_sheets_other_personas(self) -> None:
        """No ``character_sheet`` filter exists, so a mask's title is only reachable by its
        own persona id - never by asking for anything derived from the shared sheet (#3466).
        """
        mask = PersonaFactory(character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED)
        deed = LegendEntryFactory(persona=mask, title="The Masked Blade's Feat")
        PersonaTitle.objects.create(persona=mask, legend_entry=deed)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(TITLES_URL, {"persona": self.sheet.primary_persona.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert rows == []
        # But it IS reachable by its own persona id — the honest, safe parameter.
        response = self.client.get(TITLES_URL, {"persona": mask.pk})
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(rows) == 1
        assert rows[0]["title"] == "The Masked Blade's Feat"
