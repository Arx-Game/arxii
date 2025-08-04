from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB


class WebAPITests(TestCase):
    def setUp(self):
        self.account = AccountDB.objects.create_user(
            username="tester", email="tester@test.com", password="pass"
        )

    @patch("web.api.views.SESSION_HANDLER")
    def test_homepage_api_returns_stats(self, mock_session_handler):
        mock_session_handler.account_count.return_value = 0
        url = reverse("api-homepage")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page_title"], "Arx II")
        self.assertEqual(data["num_accounts_registered"], 1)
        self.assertEqual(data["num_accounts_connected"], 0)
        self.assertEqual(data["num_accounts_registered_recent"], 1)
        self.assertEqual(data["num_accounts_connected_recent"], 0)
        self.assertIsInstance(data["accounts_connected_recent"], list)

    def test_login_api_returns_user_on_post(self):
        url = reverse("api-login")
        response = self.client.post(url, {"username": "tester", "password": "pass"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "tester")
