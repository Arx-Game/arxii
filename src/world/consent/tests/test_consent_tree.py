"""Hierarchical consent-category tree + inherited defaults (#2170).

Covers ``SocialConsentCategory.ancestor_chain``, ``effective_consent_mode``, and the
inheritance/override behaviour of ``consent_blocks_targeting`` down a parent chain.
"""

from django.test import TestCase

from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
    SocialConsentWhitelistFactory,
)
from world.consent.services import consent_blocks_targeting, effective_consent_mode
from world.roster.factories import RosterTenureFactory
from world.scenes.friend_services import add_friend, declare_rival


class ConsentTreeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = RosterTenureFactory()
        cls.actor = RosterTenureFactory()
        # Root "All Antagonism" defaults opt-in; the leaf's own default is deliberately
        # EVERYONE to prove the leaf inherits the root rather than its own value.
        cls.root = SocialConsentCategoryFactory(
            key="antagonism", default_mode=ConsentMode.FRIENDS_WHITELIST
        )
        cls.leaf = SocialConsentCategoryFactory(
            key="hostile", default_mode=ConsentMode.EVERYONE, parent=cls.root
        )

    def _blocks(self, owner=None, category=None, actor=None) -> bool:
        return consent_blocks_targeting(
            owner_tenure=owner or self.owner,
            category=category or self.leaf,
            actor_tenure=actor or self.actor,
        )

    def test_ancestor_chain_is_leaf_to_root(self):
        self.assertEqual(self.leaf.ancestor_chain(), [self.leaf, self.root])
        self.assertEqual(self.root.ancestor_chain(), [self.root])

    def test_leaf_inherits_root_default_and_blocks_stranger(self):
        # No preference row, no friendship: the leaf resolves to the root's
        # FRIENDS_WHITELIST default, so a stranger is blocked despite the leaf's own
        # EVERYONE default_mode.
        self.assertTrue(self._blocks())

    def test_leaf_inherits_root_default_and_admits_friend(self):
        add_friend(friender_tenure=self.owner, friend_tenure=self.actor)
        self.assertFalse(self._blocks())

    def test_root_rule_cascades_to_leaf(self):
        pref = SocialConsentPreferenceFactory(tenure=self.owner)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.root, mode=ConsentMode.RIVALS
        )
        # Leaf now inherits RIVALS from the root; a non-rival stranger is blocked.
        self.assertEqual(effective_consent_mode(pref, self.leaf), ConsentMode.RIVALS)
        self.assertTrue(self._blocks())
        # A mutual rival passes.
        declare_rival(rivaler_tenure=self.owner, rival_tenure=self.actor)
        declare_rival(rivaler_tenure=self.actor, rival_tenure=self.owner)
        self.assertFalse(self._blocks())

    def test_leaf_rule_overrides_root_rule(self):
        pref = SocialConsentPreferenceFactory(tenure=self.owner)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.root, mode=ConsentMode.ALLOWLIST
        )
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.leaf, mode=ConsentMode.EVERYONE
        )
        # Nearest rule up the chain (the leaf's) wins over the root's.
        self.assertEqual(effective_consent_mode(pref, self.leaf), ConsentMode.EVERYONE)
        self.assertFalse(self._blocks())

    def test_parent_whitelist_admits_actor_for_child(self):
        pref = SocialConsentPreferenceFactory(tenure=self.owner)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.root, mode=ConsentMode.ALLOWLIST
        )
        # Whitelisting on the ROOT category admits the actor for the leaf too.
        SocialConsentWhitelistFactory(
            owner_tenure=self.owner, allowed_tenure=self.actor, category=self.root
        )
        self.assertFalse(self._blocks())

    def test_no_pref_row_still_resolves_root_default(self):
        bare = RosterTenureFactory()  # never touched consent settings
        self.assertTrue(self._blocks(owner=bare))  # FRIENDS_WHITELIST default → stranger blocked
        add_friend(friender_tenure=bare, friend_tenure=self.actor)
        self.assertFalse(self._blocks(owner=bare))  # friend admitted, no pref row needed

    def test_cycle_guard_terminates(self):
        # A mis-seeded cycle (root -> leaf -> root) must not hang the resolver.
        self.root.parent = self.leaf
        self.root.save(update_fields=["parent"])
        chain = self.leaf.ancestor_chain()
        self.assertEqual({c.pk for c in chain}, {self.leaf.pk, self.root.pk})
