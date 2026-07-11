"""Tests for the buildings seed helpers."""

from django.test import TestCase

from world.buildings.models import BuildingKind
from world.buildings.seeds import (
    BUILDING_PERMIT_TEMPLATE_NAME,
    HOUSE_KIND_NAME,
    ensure_building_permit_template,
    ensure_house_kind,
    ensure_plan_3_seeds,
    ensure_urban_building_kinds,
)
from world.items.models import ItemTemplate

URBAN_KIND_FLAGS = {
    "Cottage": {"is_residential": True, "is_commercial": False},
    "Tavern": {"is_residential": True, "is_commercial": True},
    "Shop": {"is_residential": False, "is_commercial": True},
    "Workshop": {"is_residential": False, "is_commercial": True},
    "Guild Hall": {"is_residential": False, "is_commercial": True},
    "Warehouse": {"is_residential": False, "is_commercial": True},
}


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


class UrbanBuildingKindsSeedTests(TestCase):
    def test_creates_all_six_urban_kinds(self) -> None:
        ensure_urban_building_kinds()
        for name, flags in URBAN_KIND_FLAGS.items():
            kind = BuildingKind.objects.get(name=name)
            for flag_name, expected in flags.items():
                self.assertEqual(
                    getattr(kind, flag_name),
                    expected,
                    f"{name}.{flag_name} should be {expected}",
                )

    def test_idempotent(self) -> None:
        ensure_urban_building_kinds()
        ensure_urban_building_kinds()
        for name in URBAN_KIND_FLAGS:
            self.assertEqual(BuildingKind.objects.filter(name=name).count(), 1)

    def test_seeded_via_plan_3_seeds(self) -> None:
        ensure_plan_3_seeds()
        for name in URBAN_KIND_FLAGS:
            self.assertTrue(BuildingKind.objects.filter(name=name).exists())
