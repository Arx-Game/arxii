"""Tests for the Builders Guild Clerk seed function."""

from django.test import TestCase

from world.buildings.factories import BuildingKindFactory
from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.factories import NPCRoleFactory
from world.npc_services.models import NPCRole, NPCServiceOffer, PermitOfferDetails
from world.npc_services.seeds import (
    BUILDERS_GUILD_CLERK_ROLE_NAME,
    _ensure_offer,
    ensure_builders_guild_clerk_role,
)


class EnsureBuildersGuildClerkRoleTests(TestCase):
    def test_creates_role_and_offers_with_permit_details(self) -> None:
        role = ensure_builders_guild_clerk_role()
        self.assertEqual(role.name, BUILDERS_GUILD_CLERK_ROLE_NAME)
        offers = list(NPCServiceOffer.objects.filter(role=role))
        self.assertGreater(len(offers), 0)
        for offer in offers:
            self.assertEqual(offer.kind, OfferKind.PERMIT)
            self.assertEqual(offer.draw_mode, DrawMode.MENU)
            # Every PERMIT offer carries a 1:1 details row (Plan 3 fills the body).
            self.assertTrue(
                PermitOfferDetails.objects.filter(offer=offer).exists(),
                f"Offer {offer.pk} ({offer.label!r}) is missing its PermitOfferDetails row",
            )

    def test_idempotent(self) -> None:
        ensure_builders_guild_clerk_role()
        ensure_builders_guild_clerk_role()
        ensure_builders_guild_clerk_role()
        self.assertEqual(NPCRole.objects.filter(name=BUILDERS_GUILD_CLERK_ROLE_NAME).count(), 1)
        # Offer count stable across re-invocations.
        offers_first_pass = list(
            NPCServiceOffer.objects.filter(role__name=BUILDERS_GUILD_CLERK_ROLE_NAME)
            .order_by("pk")
            .values_list("label", flat=True)
        )
        ensure_builders_guild_clerk_role()
        offers_second_pass = list(
            NPCServiceOffer.objects.filter(role__name=BUILDERS_GUILD_CLERK_ROLE_NAME)
            .order_by("pk")
            .values_list("label", flat=True)
        )
        self.assertEqual(offers_first_pass, offers_second_pass)


class EnsureOfferBuildingKindTests(TestCase):
    def test_building_kind_set_on_permit_details(self) -> None:
        role = NPCRoleFactory(name="test-role-for-kind")
        kind = BuildingKindFactory(name="test-kind-for-offer")
        offer = _ensure_offer(
            role=role,
            label="Test permit",
            building_kind=kind,
            max_target_size=4,
        )
        self.assertEqual(offer.permit_offer_details.building_kind, kind)
        self.assertEqual(offer.permit_offer_details.default_max_target_size, 4)

    def test_building_kind_none_leaves_unset(self) -> None:
        role = NPCRoleFactory(name="test-role-no-kind")
        offer = _ensure_offer(role=role, label="Test permit no kind")
        self.assertIsNone(offer.permit_offer_details.building_kind_id)
