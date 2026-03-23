from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, InteractionReactionFactory
from world.scenes.models import InteractionReaction


class InteractionReactionToggleTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterIdentityFactory(character=cls.character)
        cls.persona = cls.identity.active_persona

        cls.other_account = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character=cls.other_character)
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            player_data=cls.other_player_data,
            roster_entry=cls.other_roster_entry,
        )
        cls.other_identity = CharacterIdentityFactory(character=cls.other_character)
        cls.other_persona = cls.other_identity.active_persona

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_toggle_reaction_creates_on_first_call(self) -> None:
        """First POST creates a reaction."""
        interaction = InteractionFactory(persona=self.persona)
        url = reverse("interactionreaction-list")
        response = self.client.post(
            url,
            {"interaction": interaction.pk, "emoji": "\U0001f44d"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert InteractionReaction.objects.filter(
            interaction=interaction,
            account=self.account,
            emoji="\U0001f44d",
        ).exists()

    def test_toggle_reaction_deletes_on_second_call(self) -> None:
        """Second POST with same emoji removes the reaction."""
        interaction = InteractionFactory(persona=self.persona)
        url = reverse("interactionreaction-list")
        # Create
        self.client.post(
            url,
            {"interaction": interaction.pk, "emoji": "\U0001f44d"},
            format="json",
        )
        # Toggle off
        response = self.client.post(
            url,
            {"interaction": interaction.pk, "emoji": "\U0001f44d"},
            format="json",
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not InteractionReaction.objects.filter(
            interaction=interaction,
            account=self.account,
            emoji="\U0001f44d",
        ).exists()

    def test_reaction_counts_in_interaction_list(self) -> None:
        """Interaction list includes aggregated reaction counts."""
        interaction = InteractionFactory(persona=self.persona)
        InteractionReactionFactory(
            interaction=interaction,
            account=self.account,
            emoji="\U0001f44d",
        )
        InteractionReactionFactory(
            interaction=interaction,
            account=self.other_account,
            emoji="\U0001f44d",
        )
        url = reverse("interaction-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        reactions = results[0]["reactions"]
        assert len(reactions) == 1
        assert reactions[0]["emoji"] == "\U0001f44d"
        assert reactions[0]["count"] == 2

    def test_reacted_flag_true_for_reacting_user(self) -> None:
        """The reacted flag is true for the current user, false for others."""
        interaction = InteractionFactory(persona=self.persona)
        InteractionReactionFactory(
            interaction=interaction,
            account=self.account,
            emoji="\U0001f44d",
        )
        InteractionReactionFactory(
            interaction=interaction,
            account=self.other_account,
            emoji="\u2764\ufe0f",
        )
        url = reverse("interaction-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        reactions = response.data["results"][0]["reactions"]
        reaction_map = {r["emoji"]: r for r in reactions}
        assert reaction_map["\U0001f44d"]["reacted"] is True
        assert reaction_map["\u2764\ufe0f"]["reacted"] is False
