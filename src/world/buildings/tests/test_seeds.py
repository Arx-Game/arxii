"""Tests for the buildings seed helpers."""

from django.test import TestCase

from world.buildings.models import BuildingKind
from world.buildings.seeds import (
    BUILDING_PERMIT_TEMPLATE_NAME,
    HOUSE_KIND_NAME,
    ensure_building_permit_template,
    ensure_house_kind,
    ensure_plan_3_seeds,
)
from world.items.models import ItemTemplate


class BuildingPermitTemplateSeedTests(TestCase):
    def test_creates_template(self) -> None:
        template = ensure_building_permit_template()
        self.assertEqual(template.name, BUILDING_PERMIT_TEMPLATE_NAME)
        self.assertTrue(template.is_consumable)
        self.assertEqual(template.max_charges, 1)

    def test_idempotent(self) -> None:
        ensure_building_permit_template()
        ensure_building_permit_template()
        ensure_building_permit_template()
        self.assertEqual(ItemTemplate.objects.filter(name=BUILDING_PERMIT_TEMPLATE_NAME).count(), 1)


class HouseKindSeedTests(TestCase):
    def test_creates_house(self) -> None:
        house = ensure_house_kind()
        self.assertEqual(house.name, HOUSE_KIND_NAME)
        self.assertTrue(house.is_residential)
        self.assertEqual(house.rooms_per_size_tier, 20)

    def test_idempotent(self) -> None:
        ensure_house_kind()
        ensure_house_kind()
        self.assertEqual(BuildingKind.objects.filter(name=HOUSE_KIND_NAME).count(), 1)


class Plan3SeedsTests(TestCase):
    def test_seeds_everything(self) -> None:
        ensure_plan_3_seeds()
        self.assertTrue(ItemTemplate.objects.filter(name=BUILDING_PERMIT_TEMPLATE_NAME).exists())
        self.assertTrue(BuildingKind.objects.filter(name=HOUSE_KIND_NAME).exists())

    def test_wires_clerk_offers_to_house_when_present(self) -> None:
        from world.npc_services.constants import OfferKind
        from world.npc_services.models import NPCServiceOffer
        from world.npc_services.seeds import ensure_builders_guild_clerk_role

        # First seed npc_services (creates offers with no kind)
        ensure_builders_guild_clerk_role()
        # Then run Plan 3 seeds — should patch the clerk's PERMIT offers
        ensure_plan_3_seeds()
        for offer in NPCServiceOffer.objects.filter(kind=OfferKind.PERMIT):
            self.assertIsNotNone(offer.permit_offer_details.building_kind_id)
            self.assertEqual(offer.permit_offer_details.building_kind.name, HOUSE_KIND_NAME)
