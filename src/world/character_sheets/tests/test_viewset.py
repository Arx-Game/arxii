"""
Tests for the character sheets API viewset.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class TestCharacterSheetViewSet(TestCase):
    """Tests for CharacterSheetViewSet API endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared test data for all tests in the class."""
        # Original creator: player_number=1
        cls.original_player = PlayerDataFactory()
        cls.roster_entry = RosterEntryFactory()
        cls.original_tenure = RosterTenureFactory(
            player_data=cls.original_player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Second player who picked up the character: player_number=2
        cls.second_player = PlayerDataFactory()
        cls.second_tenure = RosterTenureFactory(
            player_data=cls.second_player,
            roster_entry=cls.roster_entry,
            player_number=2,
        )

        # Staff user
        cls.staff_account = AccountFactory(is_staff=True)

        # Unrelated user (no tenure on this character)
        cls.other_player = PlayerDataFactory()

    def setUp(self) -> None:
        """Set up the API client for each test."""
        self.client = APIClient()

    def test_retrieve_returns_200_for_valid_entry(self) -> None:
        """GET /api/character-sheets/{id}/ returns 200 for an existing roster entry."""
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["id"] == self.roster_entry.pk

    def test_retrieve_returns_404_for_nonexistent_entry(self) -> None:
        """GET /api/character-sheets/{id}/ returns 404 for a nonexistent ID."""
        self.client.force_authenticate(user=self.original_player.account)
        url = "/api/character-sheets/999999/"
        response = self.client.get(url)

        assert response.status_code == 404

    def test_can_edit_true_for_original_account(self) -> None:
        """Original creator (player_number=1) gets can_edit=true."""
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is True

    def test_can_edit_false_for_second_player(self) -> None:
        """Second player (player_number=2) gets can_edit=false."""
        self.client.force_authenticate(user=self.second_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False

    def test_can_edit_true_for_staff(self) -> None:
        """Staff users get can_edit=true regardless of tenure."""
        self.client.force_authenticate(user=self.staff_account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is True

    def test_can_edit_false_for_unrelated_user(self) -> None:
        """A user with no tenure on the character gets can_edit=false."""
        self.client.force_authenticate(user=self.other_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code in (401, 403)

    def test_can_edit_false_when_no_tenures_exist(self) -> None:
        """An entry with no tenures returns can_edit=false for any user."""
        empty_entry = RosterEntryFactory()
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{empty_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False
