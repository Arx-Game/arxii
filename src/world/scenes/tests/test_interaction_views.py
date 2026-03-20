from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import GuiseFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionVisibility
from world.scenes.factories import (
    InteractionAudienceFactory,
    InteractionFactory,
    PersonaFactory,
)
from world.scenes.models import InteractionFavorite


class InteractionViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # Build the full identity chain: Account -> PlayerData -> RosterTenure
        # -> RosterEntry -> character -> Guise -> Persona
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.guise = GuiseFactory(character=cls.character)
        cls.persona = PersonaFactory(guise=cls.guise)

        cls.other_account = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character=cls.other_character)
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            player_data=cls.other_player_data,
            roster_entry=cls.other_roster_entry,
        )
        cls.other_guise = GuiseFactory(character=cls.other_character)
        cls.other_persona = PersonaFactory(guise=cls.other_guise)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_list_interactions(self) -> None:
        """Authenticated users can list interactions."""
        InteractionFactory(persona=self.persona)
        InteractionFactory(persona=self.other_persona)
        url = reverse("interaction-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_by_guise(self) -> None:
        """Interactions can be filtered by guise."""
        InteractionFactory(persona=self.persona)
        InteractionFactory(persona=self.other_persona)
        url = reverse("interaction-list")
        response = self.client.get(url, {"guise": self.guise.pk})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["guise_name"] == self.guise.name

    def test_toggle_favorite_create_and_remove(self) -> None:
        """Posting to favorites creates, posting again removes."""
        interaction = InteractionFactory(persona=self.persona)
        url = reverse("interactionfavorite-list")

        # Create favorite
        response = self.client.post(url, {"interaction": interaction.pk}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert InteractionFavorite.objects.filter(
            interaction=interaction,
            roster_entry=self.roster_entry,
        ).exists()

        # Toggle off
        response = self.client.post(url, {"interaction": interaction.pk}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert not InteractionFavorite.objects.filter(
            interaction=interaction,
            roster_entry=self.roster_entry,
        ).exists()

    def test_delete_own_recent_interaction(self) -> None:
        """Writer can delete their own recent interaction."""
        interaction = InteractionFactory(persona=self.persona)
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    @suppress_permission_errors
    def test_cannot_delete_others_interaction(self) -> None:
        """Non-writer cannot delete another user's interaction.

        With privacy filtering, if the interaction is not visible to the user
        (not writer, not audience, not in a public scene), it returns 404
        rather than 403 to avoid leaking existence. If the interaction IS
        visible (e.g. via audience membership), the permission check returns 403.
        """
        # Interaction without audience membership - returns 404 (not in queryset)
        interaction = InteractionFactory(
            persona=self.other_persona,
            mode="whisper",
        )
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Interaction with audience membership - returns 403 (visible but not writer)
        visible_interaction = InteractionFactory(persona=self.other_persona)
        InteractionAudienceFactory(
            interaction=visible_interaction,
            guise=self.guise,
        )
        url = reverse("interaction-detail", kwargs={"pk": visible_interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_mark_interaction_as_very_private(self) -> None:
        """Audience member or writer can mark interaction as very_private."""
        interaction = InteractionFactory(persona=self.persona)
        InteractionAudienceFactory(
            interaction=interaction,
            guise=self.guise,
        )
        url = reverse("interaction-mark-private", kwargs={"pk": interaction.pk})
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE

    def test_retrieve_interaction_detail_includes_audience(self) -> None:
        """Detail view includes audience data."""
        interaction = InteractionFactory(persona=self.persona)
        InteractionAudienceFactory(
            interaction=interaction,
            guise=self.other_guise,
            persona=self.other_persona,
        )
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "audience" in response.data
        assert len(response.data["audience"]) == 1
