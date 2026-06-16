from django.test import TestCase

from world.consent.factories import (
    SocialConsentPreferenceFactory,
    SocialConsentWhitelistFactory,
)
from world.roster.factories import RosterTenureFactory


class SocialConsentPreferenceModelTest(TestCase):
    def test_defaults(self):
        pref = SocialConsentPreferenceFactory()
        self.assertTrue(pref.allow_social_actions)
        self.assertFalse(pref.require_whitelist)

    def test_unique_per_tenure(self):
        from django.db import IntegrityError

        tenure = RosterTenureFactory()
        SocialConsentPreferenceFactory(tenure=tenure)
        with self.assertRaises(IntegrityError):
            SocialConsentPreferenceFactory(tenure=tenure)


class SocialConsentWhitelistModelTest(TestCase):
    def test_create(self):
        entry = SocialConsentWhitelistFactory()
        self.assertIsNotNone(entry.owner_tenure_id)
        self.assertIsNotNone(entry.allowed_tenure_id)

    def test_unique_per_pair(self):
        from django.db import IntegrityError

        owner = RosterTenureFactory()
        allowed = RosterTenureFactory()
        SocialConsentWhitelistFactory(owner_tenure=owner, allowed_tenure=allowed)
        with self.assertRaises(IntegrityError):
            SocialConsentWhitelistFactory(owner_tenure=owner, allowed_tenure=allowed)
