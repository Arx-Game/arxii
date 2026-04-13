"""Tests for achievements API views."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.achievements.factories import (
    AchievementFactory,
    AchievementRewardFactory,
    CharacterAchievementFactory,
    DiscoveryFactory,
    RewardDefinitionFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class AchievementViewSetTests(TestCase):
    """Tests for AchievementViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        player_data = PlayerDataFactory(account=cls.user)
        roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # Visible achievement (not hidden)
        cls.visible_achievement = AchievementFactory(name="Visible", hidden=False)
        # Hidden achievement (not earned by user)
        cls.hidden_achievement = AchievementFactory(name="Hidden", hidden=True)
        # Hidden achievement earned by user
        cls.earned_hidden = AchievementFactory(name="EarnedHidden", hidden=True)
        CharacterAchievementFactory(character_sheet=cls.sheet, achievement=cls.earned_hidden)
        # Inactive achievement
        cls.inactive = AchievementFactory(name="Inactive", hidden=False, is_active=False)

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_shows_visible_achievements(self) -> None:
        """List endpoint returns non-hidden active achievements."""
        response = self.client.get("/api/achievements/achievements/")
        assert response.status_code == status.HTTP_200_OK
        names = [a["name"] for a in response.data]
        assert "Visible" in names

    def test_list_hides_unearned_hidden_achievements(self) -> None:
        """List endpoint does not return hidden achievements the user hasn't earned."""
        response = self.client.get("/api/achievements/achievements/")
        names = [a["name"] for a in response.data]
        assert "Hidden" not in names

    def test_list_shows_earned_hidden_achievements(self) -> None:
        """List endpoint returns hidden achievements the user has earned."""
        response = self.client.get("/api/achievements/achievements/")
        names = [a["name"] for a in response.data]
        assert "EarnedHidden" in names

    def test_list_excludes_inactive_achievements(self) -> None:
        """List endpoint does not return inactive achievements."""
        response = self.client.get("/api/achievements/achievements/")
        names = [a["name"] for a in response.data]
        assert "Inactive" not in names

    def test_list_rejects_unauthenticated(self) -> None:
        """Unauthenticated users cannot list achievements."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/achievements/achievements/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_retrieve_returns_full_detail(self) -> None:
        """Retrieve endpoint returns full achievement data with rewards."""
        reward_def = RewardDefinitionFactory(key="title.visible", name="Visible Title")
        AchievementRewardFactory(achievement=self.visible_achievement, reward=reward_def)
        response = self.client.get(f"/api/achievements/achievements/{self.visible_achievement.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Visible"
        assert "rewards" in response.data
        assert len(response.data["rewards"]) == 1
        assert response.data["rewards"][0]["reward_name"] == "Visible Title"

    def test_search_by_name(self) -> None:
        """Search filter finds achievements by name."""
        response = self.client.get("/api/achievements/achievements/?search=Visible")
        assert response.status_code == status.HTTP_200_OK
        names = [a["name"] for a in response.data]
        assert "Visible" in names


class CharacterAchievementViewSetTests(TestCase):
    """Tests for CharacterAchievementViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        player_data = PlayerDataFactory(account=cls.user)
        roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.other_character = CharacterFactory()
        cls.other_sheet = CharacterSheetFactory(character=cls.other_character)

        cls.achievement1 = AchievementFactory(name="First")
        cls.achievement2 = AchievementFactory(name="Second")

        cls.ca1 = CharacterAchievementFactory(
            character_sheet=cls.sheet, achievement=cls.achievement1
        )
        cls.ca2 = CharacterAchievementFactory(
            character_sheet=cls.other_sheet, achievement=cls.achievement2
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_character_achievements(self) -> None:
        """List endpoint returns character achievements."""
        response = self.client.get("/api/achievements/character-achievements/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_filter_by_character_sheet(self) -> None:
        """Filter by character_sheet returns only that character's achievements."""
        response = self.client.get(
            f"/api/achievements/character-achievements/?character_sheet={self.sheet.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["achievement"]["name"] == "First"

    def test_includes_discovery_info(self) -> None:
        """Character achievement includes discovery information."""
        discovery = DiscoveryFactory(achievement=self.achievement1)
        self.ca1.discovery = discovery
        self.ca1.save()

        response = self.client.get(f"/api/achievements/character-achievements/{self.ca1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_discoverer"] is True

    def test_rejects_unauthenticated(self) -> None:
        """Unauthenticated users cannot list character achievements."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/achievements/character-achievements/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
