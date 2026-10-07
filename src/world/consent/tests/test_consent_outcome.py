"""``consent_outcome``: the three-valued decision for categories that act on the target (#4187)."""

from django.test import TestCase

from world.consent.constants import ConsentMode, ConsentOutcome
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.consent.services import (
    add_social_consent_blacklist,
    add_social_consent_whitelist,
    consent_blocks_targeting,
    consent_outcome,
)
from world.roster.factories import RosterTenureFactory


class ConsentOutcomeAskingCategoryTests(TestCase):
    """A category that asks before acting (a makeover) resolves allow / ask / refuse."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = RosterTenureFactory(end_date=None)
        cls.actor = RosterTenureFactory(end_date=None)
        cls.category = SocialConsentCategoryFactory(
            key="makeover", default_mode=ConsentMode.ASK, asks_before_acting=True
        )

    def outcome(self):
        return consent_outcome(
            owner_tenure=self.owner, category=self.category, actor_tenure=self.actor
        )

    def rule(self, mode):
        pref = SocialConsentPreferenceFactory(tenure=self.owner)
        SocialConsentCategoryRuleFactory(preference=pref, category=self.category, mode=mode)
        return pref

    def test_default_ask(self):
        self.assertEqual(self.outcome(), ConsentOutcome.ASK)

    def test_everyone_allows(self):
        self.rule(ConsentMode.EVERYONE)
        self.assertEqual(self.outcome(), ConsentOutcome.ALLOW)

    def test_allowlist_refuses(self):
        self.rule(ConsentMode.ALLOWLIST)
        self.assertEqual(self.outcome(), ConsentOutcome.REFUSE)

    def test_whitelist_skips_the_ask(self):
        add_social_consent_whitelist(self.owner, self.actor, self.category)
        self.assertEqual(self.outcome(), ConsentOutcome.ALLOW)

    def test_whitelist_beats_never(self):
        self.rule(ConsentMode.ALLOWLIST)
        add_social_consent_whitelist(self.owner, self.actor, self.category)
        self.assertEqual(self.outcome(), ConsentOutcome.ALLOW)

    def test_blacklist_refuses_even_on_always_allow(self):
        self.rule(ConsentMode.EVERYONE)
        add_social_consent_blacklist(self.owner, self.actor, self.category)
        self.assertEqual(self.outcome(), ConsentOutcome.REFUSE)

    def test_master_switch_off_refuses(self):
        pref = self.rule(ConsentMode.EVERYONE)
        pref.allow_social_actions = False
        pref.save(update_fields=["allow_social_actions"])
        self.assertEqual(self.outcome(), ConsentOutcome.REFUSE)

    def test_unknown_actor_still_asks(self):
        # A sheet-less stylist (a staff puppet): the target still gets to decide.
        self.assertEqual(
            consent_outcome(owner_tenure=self.owner, category=self.category, actor_tenure=None),
            ConsentOutcome.ASK,
        )

    def test_blocks_targeting_is_refuse_only(self):
        self.assertFalse(
            consent_blocks_targeting(
                owner_tenure=self.owner, category=self.category, actor_tenure=self.actor
            )
        )
        self.rule(ConsentMode.ALLOWLIST)
        self.assertTrue(
            consent_blocks_targeting(
                owner_tenure=self.owner, category=self.category, actor_tenure=self.actor
            )
        )


class ConsentOutcomeOrdinaryCategoryTests(TestCase):
    """A category that does not ask keeps today's yes/no semantics exactly."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = RosterTenureFactory(end_date=None)
        cls.actor = RosterTenureFactory(end_date=None)
        cls.category = SocialConsentCategoryFactory(
            key="hostile", default_mode=ConsentMode.EVERYONE
        )

    def outcome(self):
        return consent_outcome(
            owner_tenure=self.owner, category=self.category, actor_tenure=self.actor
        )

    def test_everyone_allows(self):
        self.assertEqual(self.outcome(), ConsentOutcome.ALLOW)

    def test_ask_mode_on_a_non_asking_category_reads_as_everyone(self):
        pref = SocialConsentPreferenceFactory(tenure=self.owner)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.category, mode=ConsentMode.ASK
        )
        self.assertEqual(self.outcome(), ConsentOutcome.ALLOW)

    def test_blacklist_only_counts_under_all_but_blacklist(self):
        add_social_consent_blacklist(self.owner, self.actor, self.category)
        self.assertEqual(self.outcome(), ConsentOutcome.ALLOW)
        pref = SocialConsentPreferenceFactory(tenure=self.owner)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.category, mode=ConsentMode.ALL_BUT_BLACKLIST
        )
        self.assertEqual(self.outcome(), ConsentOutcome.REFUSE)
