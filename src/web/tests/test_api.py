from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB


class WebAPITests(TestCase):
    def setUp(self):
        self.account = AccountDB.objects.create_user(
            username="tester", email="tester@test.com", password="pass"
        )

    def test_homepage_api_returns_stats(self):
        url = reverse("api-homepage")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("page_title", response.json())

    def test_login_api_returns_user_on_post(self):
        url = reverse("api-login")
        response = self.client.post(url, {"username": "tester", "password": "pass"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["user"]["username"], "tester")
