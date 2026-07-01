"""Tests for world.consent.services."""

from django.test import TestCase

from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentPreferenceFactory,
)
from world.consent.models import (
    SocialConsentBlacklist,
    SocialConsentCategoryRule,
    SocialConsentWhitelist,
)
from world.consent.services import (
    add_social_consent_blacklist,
    add_social_consent_whitelist,
    get_social_consent_summary,
    remove_social_consent_blacklist,
    remove_social_consent_category_rule,
    remove_social_consent_whitelist,
    set_social_consent_category_rule,
    set_social_consent_preference,
)
from world.roster.factories import RosterTenureFactory


class ConsentServicesTests(TestCase):
    def setUp(self):
        self.owner = RosterTenureFactory()
        self.allowed = RosterTenureFactory()
        self.category = SocialConsentCategoryFactory(key="romantic")

    def test_set_social_consent_preference_creates_row(self):
        pref = set_social_consent_preference(self.owner, False)
        assert pref.allow_social_actions is False
        pref2 = set_social_consent_preference(self.owner, True)
        assert pref2.allow_social_actions is True
        assert pref2.pk == pref.pk

    def test_set_and_remove_category_rule(self):
        preference = SocialConsentPreferenceFactory(tenure=self.owner)
        rule = set_social_consent_category_rule(preference, self.category, ConsentMode.ALLOWLIST)
        assert rule.mode == ConsentMode.ALLOWLIST
        removed = remove_social_consent_category_rule(preference, self.category)
        assert removed is True
        assert not SocialConsentCategoryRule.objects.exists()

    def test_add_and_remove_whitelist(self):
        entry = add_social_consent_whitelist(self.owner, self.allowed, self.category)
        assert SocialConsentWhitelist.objects.filter(pk=entry.pk).exists()
        removed = remove_social_consent_whitelist(self.owner, self.allowed, self.category)
        assert removed is True

    def test_add_and_remove_blacklist(self):
        entry = add_social_consent_blacklist(self.owner, self.allowed, self.category)
        assert SocialConsentBlacklist.objects.filter(pk=entry.pk).exists()
        # Idempotent add returns the same row.
        again = add_social_consent_blacklist(self.owner, self.allowed, self.category)
        assert again.pk == entry.pk
        removed = remove_social_consent_blacklist(self.owner, self.allowed, self.category)
        assert removed is True
        assert not SocialConsentBlacklist.objects.exists()

    def test_summary_includes_blacklist(self):
        add_social_consent_blacklist(self.owner, self.allowed, self.category)
        summary = get_social_consent_summary(self.owner)
        assert len(summary["blacklist"]) == 1

    def test_all_four_modes_accepted(self):
        preference = SocialConsentPreferenceFactory(tenure=self.owner)
        for mode in ConsentMode.values:
            rule = set_social_consent_category_rule(preference, self.category, mode)
            assert rule.mode == mode

    def test_get_social_consent_summary_scopes_to_tenure(self):
        other = RosterTenureFactory()
        SocialConsentPreferenceFactory(tenure=other, allow_social_actions=False)
        own_pref = set_social_consent_preference(self.owner, True)
        summary = get_social_consent_summary(self.owner)
        assert summary["preference"] == own_pref
        assert len(summary["rules"]) == 0
