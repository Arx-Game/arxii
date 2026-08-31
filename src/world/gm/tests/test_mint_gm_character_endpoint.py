"""GM character mint endpoint at /api/gm/profiles/character/ (#3478 Task 3).

Moved from the world-builder app's ``mint-builder-character`` action — the
service (``mint_gm_character``) and its role gating are unchanged (#3478 Task
2); only the route and view move into the ``gm`` app.
"""

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory
from world.roster.models import RosterEntry


class TestMintGMCharacterEndpoint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_account = AccountFactory(username="mint_staff", is_staff=True)
        cls.gm_account = AccountFactory(username="mint_gm")
        GMProfileFactory(account=cls.gm_account)
        cls.plain_account = AccountFactory(username="mint_plain")

    def test_staff_account_mints_character(self):
        self.client.force_login(self.staff_account)
        resp = self.client.post(
            reverse("gm:gm-profile-character"),
            {"name": "Endpoint Staffer"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertEqual(data["name"], "Endpoint Staffer")
        self.assertTrue(
            RosterEntry.objects.filter(character_sheet_id=data["character_id"]).exists()
        )

    def test_gm_account_mints_character(self):
        self.client.force_login(self.gm_account)
        resp = self.client.post(
            reverse("gm:gm-profile-character"),
            {"name": "Endpoint Storyteller"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertEqual(data["name"], "Endpoint Storyteller")
        self.assertTrue(
            RosterEntry.objects.filter(character_sheet_id=data["character_id"]).exists()
        )

    def test_plain_account_refused(self):
        self.client.force_login(self.plain_account)
        resp = self.client.post(
            reverse("gm:gm-profile-character"),
            {"name": "Sneaky Endpoint"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())
        self.assertFalse(
            RosterEntry.objects.filter(
                character_sheet__character__db_key="Sneaky Endpoint"
            ).exists()
        )

    def test_duplicate_name_returns_user_message(self):
        # Two distinct staff accounts (#3478's one-GM-character-per-account
        # guard would otherwise fire first on a same-account retry, masking
        # the name-uniqueness check this test targets — see
        # world.roster.tests.test_staff_characters).
        other_staff = AccountFactory(username="mint_staff_two", is_staff=True)
        self.client.force_login(self.staff_account)
        first = self.client.post(
            reverse("gm:gm-profile-character"),
            {"name": "Twin Endpoint Name"},
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 201, first.content)

        self.client.force_login(other_staff)
        second = self.client.post(
            reverse("gm:gm-profile-character"),
            {"name": "twin endpoint name"},
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn("already exists", second.json()["detail"])
