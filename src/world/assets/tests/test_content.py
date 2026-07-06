"""Seed content tests for the promotion demo (#1872)."""

from __future__ import annotations

from django.test import TestCase

from world.assets.content import ensure_asset_promotion_content
from world.npc_services.constants import OfferKind
from world.npc_services.models import NPCServiceOffer


class EnsureAssetPromotionContentTests(TestCase):
    def test_seeds_six_offers_on_one_role(self) -> None:
        role = ensure_asset_promotion_content()
        offers = NPCServiceOffer.objects.filter(role=role)
        kinds = set(offers.values_list("kind", flat=True))
        self.assertEqual(
            kinds,
            {
                OfferKind.INFORMANT.value,
                OfferKind.CONTACT.value,
                OfferKind.PERSONAL_FAVOR.value,
                OfferKind.GUARD.value,
                OfferKind.FAN.value,
                OfferKind.MINOR_ALLY.value,
            },
        )

    def test_idempotent(self) -> None:
        ensure_asset_promotion_content()
        role = ensure_asset_promotion_content()
        self.assertEqual(NPCServiceOffer.objects.filter(role=role).count(), 6)

    def test_offers_reuse_existing_check_types_not_new_ones(self) -> None:
        ensure_asset_promotion_content()
        role = NPCServiceOffer.objects.filter(kind=OfferKind.INFORMANT.value).first().role
        offers = NPCServiceOffer.objects.filter(role=role)
        check_type_by_kind = dict(offers.values_list("kind", "check_type__name"))
        # Asserting these three exact (kind, check_type name) pairs — rather than a
        # bare CheckType.objects.count() — is the robust check: the three seed
        # functions (seed_stealth_check_content/seed_governance_check_content/
        # seed_social_check_content) each seed their own broader content, so a
        # total-row-count assertion would be fragile against unrelated CheckType
        # rows those seeders also produce.
        self.assertEqual(
            check_type_by_kind,
            {
                OfferKind.INFORMANT.value: "Stealth",
                OfferKind.CONTACT.value: "Household Command",
                OfferKind.PERSONAL_FAVOR.value: "Seduction",
                OfferKind.GUARD.value: "Intimidation",
                OfferKind.FAN.value: "Gossip",
                OfferKind.MINOR_ALLY.value: "Domain Investment",
            },
        )
