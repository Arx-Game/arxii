"""GET/PATCH /api/account/security-settings/ (#3591, decision 5)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData

URL = "/api/account/security-settings/"


class AccountSecuritySettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="secsettings_user")
        PlayerData.objects.get_or_create(account=cls.account)

    def setUp(self):
        self.client = APIClient()

    def test_anonymous_is_403(self):
        # SessionAuthentication has no authenticate header, so DRF answers 403
        # for anonymous, not 401.
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_get_defaults_to_false(self):
        self.client.force_authenticate(self.account)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"block_telnet_login_with_2fa": False})

    def test_patch_flips_the_flag_and_persists(self):
        self.client.force_authenticate(self.account)
        response = self.client.patch(URL, {"block_telnet_login_with_2fa": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"block_telnet_login_with_2fa": True})
        self.assertTrue(PlayerData.objects.get(account=self.account).block_telnet_login_with_2fa)

    def test_patch_rejects_a_non_boolean(self):
        self.client.force_authenticate(self.account)
        response = self.client.patch(URL, {"block_telnet_login_with_2fa": "later"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
