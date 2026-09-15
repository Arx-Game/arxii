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


class PersonaFilterByCharacterSheetTestCase(APITestCase):
    """``?character_sheet=<pk>`` is the in-game persona fetch, and it must not 500.

    ``frontend/src/game/personaQueries.ts`` requests
    ``/api/personas/?character_sheet=<pk>&page_size=100`` for the PersonaSwitcher,
    SelectedCharacterChip and PersonaTiles. The filter used to declare
    ``field_name="character_sheet__id"``, but CharacterSheet's pk IS its
    ``character`` OneToOne (``primary_key=True``), so there is no ``id`` field to
    traverse to and Django parsed the segment as a lookup on the ForeignKey:
    ``FieldError: Unsupported lookup 'id__exact' for ForeignKey``. Every one of
    those requests was a 500 in production (digest #3736).
    """

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_filtering_by_character_sheet_returns_only_that_sheets_personas(self) -> None:
        Persona.objects.all().delete()
        mine = CharacterSheetFactory()
        theirs = CharacterSheetFactory()
        wanted = PersonaFactory(character_sheet=mine, name="Wanted")
        unwanted = PersonaFactory(character_sheet=theirs, name="Unwanted")

        response = self.client.get(reverse("persona-list"), {"character_sheet": mine.pk})

        assert response.status_code == status.HTTP_200_OK
        returned_ids = {row["id"] for row in response.data["results"]}
        assert wanted.id in returned_ids
        assert unwanted.id not in returned_ids
