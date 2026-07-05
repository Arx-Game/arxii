"""Seed content tests for the promotion demo (#1872)."""

from __future__ import annotations

from django.test import TestCase

from world.assets.content import ensure_asset_promotion_content
from world.npc_services.constants import OfferKind
from world.npc_services.models import NPCServiceOffer


class EnsureAssetPromotionContentTests(TestCase):
    def test_seeds_three_offers_on_one_role(self) -> None:
        role = ensure_asset_promotion_content()
        offers = NPCServiceOffer.objects.filter(role=role)
        kinds = set(offers.values_list("kind", flat=True))
        self.assertEqual(
            kinds,
            {OfferKind.INFORMANT.value, OfferKind.CONTACT.value, OfferKind.PERSONAL_FAVOR.value},
        )

    def test_idempotent(self) -> None:
        ensure_asset_promotion_content()
        role = ensure_asset_promotion_content()
        self.assertEqual(NPCServiceOffer.objects.filter(role=role).count(), 3)

    def test_offers_reuse_existing_check_types_not_new_ones(self) -> None:
        ensure_asset_promotion_content()
        names = set(
            NPCServiceOffer.objects.filter(kind=OfferKind.INFORMANT.value).values_list(
                "check_type__name", flat=True
            )
        )
        self.assertIn("Stealth", names)
