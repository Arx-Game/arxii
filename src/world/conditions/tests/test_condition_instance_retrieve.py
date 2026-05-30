"""Tests for the single-instance ConditionInstance retrieve route (#551).

Verifies ``GET /api/conditions/instances/<pk>/`` returns a condition
instance the requesting account owns (target character is one of the
account's available characters) and 404s for instances on characters the
requester does not own (queryset-scoped, matching the list view's scoping).
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


def _give_account_character(account, character):
    """Wire ``account`` so ``get_available_characters()`` returns ``character``."""
    player_data = PlayerDataFactory(account=account)
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    CharacterSheetFactory(character=character)


class ConditionInstanceRetrieveTests(APITestCase):
    """Tests for the single ConditionInstance retrieve endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        _give_account_character(cls.user, cls.character)

        cls.condition = ConditionTemplateFactory(name="Concussed")
        cls.instance = ConditionInstanceFactory(
            target=cls.character,
            condition=cls.condition,
            severity=2,
        )

        # A separate account that does NOT own cls.character.
        cls.other_user = AccountFactory()
        cls.other_character = CharacterFactory()
        _give_account_character(cls.other_user, cls.other_character)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user)

    def test_retrieve_owned_condition_instance(self) -> None:
        """Owner gets 200 with the instance id and serializer fields."""
        response = self.client.get(f"/api/conditions/instances/{self.instance.pk}/")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["id"] == self.instance.pk
        assert response.data["name"] == "Concussed"
        assert response.data["severity"] == 2

    def test_retrieve_unowned_condition_instance_returns_404(self) -> None:
        """A different account cannot retrieve an instance it doesn't own."""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(f"/api/conditions/instances/{self.instance.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND, response.data

    def test_retrieve_unauthenticated_denied(self) -> None:
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/conditions/instances/{self.instance.pk}/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
