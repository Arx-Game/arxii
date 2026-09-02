"""Own-GM-profile read/update endpoint (#3478)."""

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps


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

    def test_no_cap_row_for_the_profiles_level_gets_none_and_false(self):
        """No GMLevelCap seeded at all -> the most-restrictive fallback (#3562)."""
        self.client.force_login(self.account)
        resp = self.client.get(reverse("gm:gm-profile-mine"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["max_beat_risk"], "none")
        self.assertFalse(resp.json()["allow_custom_stakes"])

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


class TestGMProfileMineCapFields(TestCase):
    """max_beat_risk / allow_custom_stakes surface the caller's GMLevelCap (#3562)."""

    @classmethod
    def setUpTestData(cls):
        cls.caps = seed_default_gm_level_caps()
        cls.junior_account = AccountFactory()
        cls.junior_profile = GMProfileFactory(account=cls.junior_account, level=GMLevel.JUNIOR)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.staff_profile = GMProfileFactory(account=cls.staff_account, level=GMLevel.STARTING)

    def test_junior_gm_gets_its_cap_rows_values(self):
        self.client.force_login(self.junior_account)
        resp = self.client.get(reverse("gm:gm-profile-mine"))
        self.assertEqual(resp.status_code, 200)
        cap = self.caps[GMLevel.JUNIOR]
        self.assertEqual(resp.json()["max_beat_risk"], cap.max_beat_risk)
        self.assertEqual(resp.json()["allow_custom_stakes"], cap.allow_custom_stakes)

    def test_staff_gets_extreme_and_true_regardless_of_its_own_cap(self):
        self.client.force_login(self.staff_account)
        resp = self.client.get(reverse("gm:gm-profile-mine"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["max_beat_risk"], "extreme")
        self.assertTrue(resp.json()["allow_custom_stakes"])

    def test_patch_cannot_set_max_beat_risk(self):
        """max_beat_risk is a SerializerMethodField: PATCH body is silently ignored."""
        self.client.force_login(self.junior_account)
        resp = self.client.patch(
            reverse("gm:gm-profile-mine"),
            {"max_beat_risk": "extreme", "allow_custom_stakes": True},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        cap = self.caps[GMLevel.JUNIOR]
        self.assertEqual(resp.json()["max_beat_risk"], cap.max_beat_risk)
        self.assertEqual(resp.json()["allow_custom_stakes"], cap.allow_custom_stakes)
