"""PersonaViewSet visibility: OOC system/narrator personas are hidden (#643)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.scenes.models import Persona


class PersonaViewSetSystemVisibilityTestCase(APITestCase):
    """The combat Narrator (is_system=True) must not appear in the persona picker."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_system_personas_excluded_from_list(self) -> None:
        Persona.objects.all().delete()
        identity = CharacterSheetFactory()
        player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(
            account=self.account,
        )
        roster_entry = RosterEntryFactory(character_sheet__character=identity.character)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)

        visible = PersonaFactory(character_sheet=identity.character.sheet_data, name="Visible")
        hidden = PersonaFactory(
            character_sheet=identity.character.sheet_data,
            name="SystemNarrator",
            is_system=True,
        )

        response = self.client.get(reverse("persona-list"))

        assert response.status_code == status.HTTP_200_OK
        returned_ids = {row["id"] for row in response.data["results"]}
        assert visible.id in returned_ids
        assert hidden.id not in returned_ids
