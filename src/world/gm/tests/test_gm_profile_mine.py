"""Own-GM-profile read/update endpoint (#3478)."""

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory


class TestGMProfileMine(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gm_profile = GMProfileFactory()
        cls.account = cls.gm_profile.account
        cls.other = AccountFactory()

    def test_gm_reads_own_profile(self):
        self.client.force_login(self.account)
        resp = self.client.get(reverse("gm:gm-profile-mine"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["contact_times"], "")

    def test_gm_updates_operational_fields(self):
        self.client.force_login(self.account)
        resp = self.client.patch(
            reverse("gm:gm-profile-mine"),
            {"contact_times": "Weekends EST", "ooc_info": "Be kind."},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.gm_profile.refresh_from_db()
        self.assertEqual(self.gm_profile.contact_times, "Weekends EST")

    def test_level_is_not_writable(self):
        self.client.force_login(self.account)
        self.client.patch(
            reverse("gm:gm-profile-mine"), {"level": "senior"}, content_type="application/json"
        )
        self.gm_profile.refresh_from_db()
        self.assertNotEqual(self.gm_profile.level, "senior")

    def test_non_gm_gets_404(self):
        self.client.force_login(self.other)
        resp = self.client.get(reverse("gm:gm-profile-mine"))
        self.assertEqual(resp.status_code, 404)
