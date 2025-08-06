"""
Tests for roster views and API endpoints.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class RosterEntryViewSetTestCase(TestCase):
    """Test RosterEntryViewSet API endpoints"""

    def setUp(self):
        """Set up test data for each test"""
        self.roster_entry = RosterEntryFactory()
        self.tenure = RosterTenureFactory(roster_entry=self.roster_entry)
        self.client = APIClient()

    def test_roster_list_endpoint_evaluates_without_error(self):
        """Test that the roster list endpoint works without queryset AttributeError"""
        response = self.client.get("/api/roster/")

        # Should not raise an AttributeError about missing 'tenures' relationship
        self.assertEqual(response.status_code, 200)

        # Verify the response contains our roster entry
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.roster_entry.id)

    def test_roster_detail_endpoint_prefetches_tenures_correctly(self):
        """Test that the detail endpoint properly uses prefetched tenure data"""
        response = self.client.get(f"/api/roster/{self.roster_entry.id}/")

        # Should work without database errors
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.roster_entry.id)

        # Should include character data
        self.assertIn("character", response.data)
        self.assertEqual(
            response.data["character"]["name"], self.roster_entry.character.name
        )
