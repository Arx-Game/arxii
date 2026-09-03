"""cap_for_profile + gm_max_risk delegation (#3562)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.gm.services import cap_for_profile, gm_max_risk
from world.societies.constants import RenownRisk


class TestCapForProfile(TestCase):
    def test_returns_the_row_for_the_profiles_level(self):
        caps = seed_default_gm_level_caps()
        profile = GMProfileFactory(level=GMLevel.JUNIOR)
        self.assertEqual(cap_for_profile(profile), caps[GMLevel.JUNIOR])

    def test_returns_none_when_the_level_is_unseeded(self):
        profile = GMProfileFactory(level=GMLevel.JUNIOR)
        self.assertIsNone(cap_for_profile(profile))


class TestGmMaxRiskDelegatesToCapForProfile(TestCase):
    def test_delegates_to_the_seeded_cap(self):
        seed_default_gm_level_caps()
        profile = GMProfileFactory(level=GMLevel.JUNIOR, account=AccountFactory())
        self.assertEqual(gm_max_risk(profile.account), RenownRisk.MODERATE)

    def test_no_cap_row_is_none(self):
        profile = GMProfileFactory(level=GMLevel.JUNIOR, account=AccountFactory())
        self.assertEqual(gm_max_risk(profile.account), RenownRisk.NONE)

    def test_no_gm_profile_is_none(self):
        account = AccountFactory()
        self.assertEqual(gm_max_risk(account), RenownRisk.NONE)
