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
        entry = SocialConsentWhitelistFactory(owner_tenure=owner, allowed_tenure=allowed)
        with self.assertRaises(IntegrityError):
            SocialConsentWhitelistFactory(
                owner_tenure=owner, allowed_tenure=allowed, category=entry.category
            )


class SocialConsentCategoryRuleModelTest(TestCase):
    def test_category_rule_unique_per_category(self):
        from django.db import IntegrityError

        from world.consent.constants import ConsentMode
        from world.consent.factories import (
            SocialConsentCategoryFactory,
            SocialConsentCategoryRuleFactory,
            SocialConsentPreferenceFactory,
        )

        pref = SocialConsentPreferenceFactory()
        cat = SocialConsentCategoryFactory()
        SocialConsentCategoryRuleFactory(preference=pref, category=cat, mode=ConsentMode.ALLOWLIST)
        with self.assertRaises(IntegrityError):
            SocialConsentCategoryRuleFactory(preference=pref, category=cat)

    def test_whitelist_unique_per_owner_allowed_category(self):
        from django.db import IntegrityError

        from world.consent.factories import (
            SocialConsentCategoryFactory,
            SocialConsentWhitelistFactory,
        )
        from world.roster.factories import RosterTenureFactory

        owner, allowed = RosterTenureFactory(), RosterTenureFactory()
        cat = SocialConsentCategoryFactory()
        SocialConsentWhitelistFactory(owner_tenure=owner, allowed_tenure=allowed, category=cat)
        with self.assertRaises(IntegrityError):
            SocialConsentWhitelistFactory(owner_tenure=owner, allowed_tenure=allowed, category=cat)
