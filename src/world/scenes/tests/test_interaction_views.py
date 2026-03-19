from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.constants import InteractionVisibility
from world.scenes.factories import (
    InteractionAudienceFactory,
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.models import InteractionFavorite


class InteractionViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.location = ObjectDBFactory(
            db_key="test-room",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        cls.other_account = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character=cls.other_character)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)
        self.puppet_patcher = patch.object(
            type(self.account),
            "get_puppeted_characters",
            return_value=[self.character],
        )
        self.puppet_patcher.start()

    def tearDown(self) -> None:
        self.puppet_patcher.stop()

    def test_list_interactions(self) -> None:
        """Authenticated users can list interactions."""
        InteractionFactory(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
        )
        InteractionFactory(
            character=self.other_character,
            roster_entry=self.other_roster_entry,
            location=self.location,
        )
        url = reverse("interaction-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_by_character(self) -> None:
        """Interactions can be filtered by character."""
        InteractionFactory(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
        )
        InteractionFactory(
            character=self.other_character,
            roster_entry=self.other_roster_entry,
            location=self.location,
        )
        url = reverse("interaction-list")
        response = self.client.get(url, {"character": self.character.pk})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["character_name"] == self.character.db_key

    def test_toggle_favorite_create_and_remove(self) -> None:
        """Posting to favorites creates, posting again removes."""
        interaction = InteractionFactory(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
        )
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
        interaction = InteractionFactory(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
        )
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    @suppress_permission_errors
    def test_cannot_delete_others_interaction(self) -> None:
        """Non-writer cannot delete another user's interaction."""
        interaction = InteractionFactory(
            character=self.other_character,
            roster_entry=self.other_roster_entry,
            location=self.location,
        )
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_mark_interaction_as_very_private(self) -> None:
        """Audience member or writer can mark interaction as very_private."""
        interaction = InteractionFactory(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
        )
        InteractionAudienceFactory(
            interaction=interaction,
            roster_entry=self.roster_entry,
        )
        url = reverse("interaction-mark-private", kwargs={"pk": interaction.pk})
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE

    def test_retrieve_interaction_detail_includes_audience(self) -> None:
        """Detail view includes audience data."""
        interaction = InteractionFactory(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
        )
        scene = SceneFactory()
        participation = SceneParticipationFactory(scene=scene, account=self.account)
        persona = PersonaFactory(participation=participation, character=self.character)
        InteractionAudienceFactory(
            interaction=interaction,
            roster_entry=self.roster_entry,
            persona=persona,
        )
        url = reverse("interaction-detail", kwargs={"pk": interaction.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "audience" in response.data
        assert len(response.data["audience"]) == 1
        assert response.data["audience"][0]["persona_name"] == persona.name
