"""Category default_mode + the theft gate helper (#1909)."""

from django.test import TestCase

from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.consent.services import consent_blocks_targeting, theft_category
from world.roster.factories import RosterTenureFactory


class DefaultModeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_tenure = RosterTenureFactory()
        cls.actor_tenure = RosterTenureFactory()
        cls.pref = SocialConsentPreferenceFactory(tenure=cls.owner_tenure)

    def test_absent_rule_uses_category_default_mode_everyone(self):
        category = SocialConsentCategoryFactory(default_mode=ConsentMode.EVERYONE)
        self.assertFalse(
            consent_blocks_targeting(
                owner_tenure=self.owner_tenure, category=category, actor_tenure=self.actor_tenure
            )
        )

    def test_absent_rule_uses_category_default_mode_allowlist(self):
        category = SocialConsentCategoryFactory(default_mode=ConsentMode.ALLOWLIST)
        self.assertTrue(
            consent_blocks_targeting(
                owner_tenure=self.owner_tenure, category=category, actor_tenure=self.actor_tenure
            )
        )

    def test_explicit_rule_beats_default_mode(self):
        category = SocialConsentCategoryFactory(default_mode=ConsentMode.ALLOWLIST)
        SocialConsentCategoryRuleFactory(
            preference=self.pref, category=category, mode=ConsentMode.EVERYONE
        )
        self.assertFalse(
            consent_blocks_targeting(
                owner_tenure=self.owner_tenure, category=category, actor_tenure=self.actor_tenure
            )
        )

    def test_theft_category_lazy_created_default_deny(self):
        category = theft_category()
        self.assertEqual(category.key, "theft")
        self.assertEqual(category.default_mode, ConsentMode.ALLOWLIST)
        # Absent rule → nobody may steal from this tenure.
        self.assertTrue(
            consent_blocks_targeting(
                owner_tenure=self.owner_tenure, category=category, actor_tenure=self.actor_tenure
            )
        )

    def test_no_preference_row_blocks_for_default_deny_category(self):
        bare_tenure = RosterTenureFactory()  # no SocialConsentPreference row at all
        self.assertTrue(
            consent_blocks_targeting(
                owner_tenure=bare_tenure, category=theft_category(), actor_tenure=self.actor_tenure
            )
        )
