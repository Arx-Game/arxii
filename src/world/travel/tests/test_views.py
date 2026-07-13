"""Tests for travel API views (#2352)."""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.travel.factories import TravelHubFactory, TravelMethodFactory


class TravelHubViewSetTests(APITestCase):
    def setUp(self):
        self.account = AccountFactory()

    def test_requires_auth(self):
        response = self.client.get("/api/travel/hubs/")
        self.assertIn(response.status_code, (401, 403))

    def test_returns_active_hubs(self):
        TravelHubFactory(name="Test Hub", is_active=True)
        self.client.force_authenticate(user=self.account)

        response = self.client.get("/api/travel/hubs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Test Hub")

    def test_excludes_inactive_hubs(self):
        TravelHubFactory(name="Active Hub", is_active=True)
        TravelHubFactory(name="Inactive Hub", is_active=False)
        self.client.force_authenticate(user=self.account)

        response = self.client.get("/api/travel/hubs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Active Hub")


class TravelMethodViewSetTests(APITestCase):
    def setUp(self):
        self.account = AccountFactory()

    def test_requires_auth(self):
        response = self.client.get("/api/travel/methods/")
        self.assertIn(response.status_code, (401, 403))

    def test_returns_methods(self):
        TravelMethodFactory(name="Walking")
        TravelMethodFactory(name="Sailing")
        self.client.force_authenticate(user=self.account)

        response = self.client.get("/api/travel/methods/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)


class VoyageViewSetTests(APITestCase):
    def setUp(self):
        self.account = AccountFactory()

    def test_requires_auth(self):
        response = self.client.get("/api/travel/voyages/")
        self.assertIn(response.status_code, (401, 403))

    def test_returns_empty_for_no_voyages(self):
        self.client.force_authenticate(user=self.account)

        response = self.client.get("/api/travel/voyages/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)


class VoyageInviteViewSetTests(APITestCase):
    def setUp(self):
        self.account = AccountFactory()

    def test_requires_auth(self):
        response = self.client.get("/api/travel/invites/")
        self.assertIn(response.status_code, (401, 403))

    def test_returns_empty_for_no_invites(self):
        self.client.force_authenticate(user=self.account)

        response = self.client.get("/api/travel/invites/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)
