"""Consent seed — the antagonism category tree + inherited opt-in default (#1680/#2170).

The seed builds an **All Antagonism** root (FRIENDS_WHITELIST) and parents the antagonism
leaves (Hostile, Blackmail) under it, so they inherit the opt-in default while keeping their
own ``default_mode`` field legible for the orphaned-row case. Romantic/Manipulative/General
stay independent default-allow roots.
"""

from django.test import TestCase

from world.consent.constants import ConsentMode
from world.consent.models import SocialConsentCategory
from world.consent.services import effective_consent_mode
from world.seeds.consent import _TEMPLATE_CATEGORY_MAP, seed_social_consent_categories


class BlackmailConsentCategoryTests(TestCase):
    def test_seeds_blackmail_category_with_optin_default(self) -> None:
        seed_social_consent_categories()
        cat = SocialConsentCategory.objects.get(key="blackmail")
        self.assertEqual(cat.name, "Blackmail")
        self.assertEqual(cat.default_mode, ConsentMode.FRIENDS_WHITELIST)

    def test_legacy_leaf_default_mode_field_unchanged(self) -> None:
        # A leaf's own ``default_mode`` field is left as-is (only the root's is consulted
        # while parented) — Hostile stays EVERYONE on the field, but *inherits* the root.
        seed_social_consent_categories()
        for key in ("romantic", "hostile", "manipulative", "general"):
            self.assertEqual(
                SocialConsentCategory.objects.get(key=key).default_mode,
                ConsentMode.EVERYONE,
            )

    def test_antagonism_root_and_tree_wired(self) -> None:
        seed_social_consent_categories()
        root = SocialConsentCategory.objects.get(key="antagonism")
        self.assertEqual(root.default_mode, ConsentMode.FRIENDS_WHITELIST)
        self.assertIsNone(root.parent_id)
        # Every detriment-capable category hangs under All Antagonism (#2170) — including
        # theft, whose effective default therefore moves from ALLOWLIST to FRIENDS_WHITELIST.
        for key in ("hostile", "blackmail", "manipulative", "theft"):
            leaf = SocialConsentCategory.objects.get(key=key)
            self.assertEqual(leaf.parent_id, root.pk, msg=f"{key} should hang under All Antagonism")
            # No preference row → the leaf resolves to the root's opt-in default via inheritance.
            self.assertEqual(effective_consent_mode(None, leaf), ConsentMode.FRIENDS_WHITELIST)

    def test_romantic_and_general_stay_independent_roots(self) -> None:
        seed_social_consent_categories()
        for key in ("romantic", "general"):
            cat = SocialConsentCategory.objects.get(key=key)
            self.assertIsNone(cat.parent_id, msg=f"{key} stays an independent EVERYONE root")
            self.assertEqual(effective_consent_mode(None, cat), ConsentMode.EVERYONE)

    def test_idempotent(self) -> None:
        seed_social_consent_categories()
        seed_social_consent_categories()
        self.assertEqual(SocialConsentCategory.objects.filter(key="blackmail").count(), 1)
        # Re-running does not duplicate or unset the parent link.
        self.assertEqual(SocialConsentCategory.objects.get(key="hostile").parent.key, "antagonism")

    def test_blackmail_template_mapped_to_blackmail_category(self) -> None:
        self.assertEqual(_TEMPLATE_CATEGORY_MAP["Blackmail"], "blackmail")
