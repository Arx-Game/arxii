"""Styling seed content (#2632) — idempotency + graceful trait-less skip."""

from __future__ import annotations

from django.test import TestCase

from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.npc_services.models import NPCServiceOffer, StylingOfferDetails
from world.seeds.styling import (
    PROFILE_SCRIBE_ROLE_NAME,
    STYLIST_ROLE_NAME,
    seed_styling_content,
)


class StylingSeedTests(TestCase):
    def _seed_traits(self) -> None:
        hair_color = FormTraitFactory(
            name="hair_color", display_name="Hair Color", is_cosmetic=True
        )
        FormTraitOptionFactory(trait=hair_color, name="red", display_name="Red")
        hair_style = FormTraitFactory(
            name="hair_style", display_name="Hair Style", is_cosmetic=True
        )
        FormTraitOptionFactory(trait=hair_style, name="braided", display_name="Braided")
        FormTraitFactory(name="eye_color", display_name="Eye Color", is_cosmetic=True)

    def test_seed_is_idempotent(self) -> None:
        self._seed_traits()
        seed_styling_content()
        first_count = NPCServiceOffer.objects.count()
        seed_styling_content()
        self.assertEqual(NPCServiceOffer.objects.count(), first_count)

    def test_seeds_stylist_offers_and_scribe(self) -> None:
        self._seed_traits()
        seed_styling_content()

        stylist_offers = NPCServiceOffer.objects.filter(role__name=STYLIST_ROLE_NAME)
        self.assertEqual(stylist_offers.count(), 2)  # red + braided
        self.assertEqual(StylingOfferDetails.objects.count(), 2)
        self.assertTrue(
            NPCServiceOffer.objects.filter(role__name=PROFILE_SCRIBE_ROLE_NAME).exists()
        )

    def test_seed_without_traits_skips_gracefully(self) -> None:
        seed_styling_content()
        self.assertEqual(NPCServiceOffer.objects.filter(role__name=STYLIST_ROLE_NAME).count(), 0)
        self.assertTrue(
            NPCServiceOffer.objects.filter(role__name=PROFILE_SCRIBE_ROLE_NAME).exists()
        )
