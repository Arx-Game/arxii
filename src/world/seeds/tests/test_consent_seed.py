"""Consent seed — the blackmail antagonism category (#1680).

Blackmail leads the antagonism categories to Apostate's ratified opt-in default
(FRIENDS_WHITELIST), while the legacy categories keep their default-allow behavior.
"""

from django.test import TestCase

from world.consent.constants import ConsentMode
from world.consent.models import SocialConsentCategory
from world.seeds.consent import _TEMPLATE_CATEGORY_MAP, seed_social_consent_categories


class BlackmailConsentCategoryTests(TestCase):
    def test_seeds_blackmail_category_with_optin_default(self) -> None:
        seed_social_consent_categories()
        cat = SocialConsentCategory.objects.get(key="blackmail")
        self.assertEqual(cat.name, "Blackmail")
        self.assertEqual(cat.default_mode, ConsentMode.FRIENDS_WHITELIST)

    def test_legacy_categories_keep_default_allow(self) -> None:
        seed_social_consent_categories()
        for key in ("romantic", "hostile", "manipulative", "general"):
            self.assertEqual(
                SocialConsentCategory.objects.get(key=key).default_mode,
                ConsentMode.EVERYONE,
                msg=f"{key} should stay default-allow (the #2170 default audit is separate)",
            )

    def test_idempotent(self) -> None:
        seed_social_consent_categories()
        seed_social_consent_categories()
        self.assertEqual(SocialConsentCategory.objects.filter(key="blackmail").count(), 1)

    def test_blackmail_template_mapped_to_blackmail_category(self) -> None:
        self.assertEqual(_TEMPLATE_CATEGORY_MAP["Blackmail"], "blackmail")
