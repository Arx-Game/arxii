"""
Tests for roster views and API endpoints.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class RosterEntryViewSetTestCase(TestCase):
    """Test RosterEntryViewSet API endpoints"""

    def setUp(self):
        """Set up test data for each test"""
        self.roster_entry = RosterEntryFactory()
        self.sheet = CharacterSheetFactory(
            character=self.roster_entry.character,
            age=30,
            gender="male",
            concept="Brave knight",
            family="Stormwind",
            vocation="Warrior",
            social_rank=5,
            background="Born into nobility",
        )
        self.tenure = RosterTenureFactory(roster_entry=self.roster_entry)
        self.client = APIClient()

    def test_mine_endpoint_with_authentication(self):
        """Test that mine endpoint works with authentication"""
        from django.contrib.auth import get_user_model

        from evennia_extensions.models import PlayerData

        User = get_user_model()
        user = User.objects.create_user(username="testuser", password="password")
        PlayerData.objects.create(account=user)

        # Authenticate the client
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/roster/entries/mine/")

        # Should return JSON response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIsInstance(response.data, list)

    def test_roster_list_endpoint_evaluates_without_error(self):
        """Test roster list endpoint works without queryset AttributeError"""
        response = self.client.get("/api/roster/entries/")

        # Should not raise AttributeError about missing 'tenures' relationship
        self.assertEqual(response.status_code, 200)

        # Verify response contains our roster entry within paginated results
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.roster_entry.id)

    def test_roster_detail_endpoint_prefetches_tenures_correctly(self):
        """Test detail endpoint properly uses prefetched tenure data"""
        response = self.client.get(f"/api/roster/entries/{self.roster_entry.id}/")

        # Should work without database errors
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.roster_entry.id)

        # Should include character data and nested structures
        self.assertIn("character", response.data)
        self.assertIn("profile_picture", response.data)
        self.assertIn("tenures", response.data)
        character = response.data["character"]
        self.assertEqual(character["name"], self.roster_entry.character.name)
        self.assertEqual(character["age"], self.sheet.age)
        self.assertEqual(character["gender"], self.sheet.gender)
        self.assertEqual(character["concept"], self.sheet.concept)
        self.assertEqual(character["family"], self.sheet.family)
        self.assertEqual(character["vocation"], self.sheet.vocation)
        self.assertEqual(character["social_rank"], self.sheet.social_rank)
        self.assertEqual(character["background"], self.sheet.background)
        self.assertIsNone(character["race"])
        self.assertIsNone(character["char_class"])
        self.assertIsNone(character["level"])

    def test_filter_by_name_returns_expected_entry(self):
        """Ensure filtering by name works."""
        RosterEntryFactory()
        response = self.client.get(
            f"/api/roster/entries/?name={self.roster_entry.character.db_key}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.roster_entry.id)
