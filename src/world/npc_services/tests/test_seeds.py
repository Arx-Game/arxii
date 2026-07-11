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


class ClerkOfferWiringTests(TestCase):
    def setUp(self) -> None:
        from world.buildings.seeds import ensure_urban_building_kinds

        ensure_urban_building_kinds()

    def test_creates_seven_permit_offers_wired_to_kinds(self) -> None:
        role = ensure_builders_guild_clerk_role()
        permit_offers = NPCServiceOffer.objects.filter(role=role, kind=OfferKind.PERMIT)
        # All 9 offers have kind=PERMIT; the 7 kind-specific ones have
        # building_kind wired, the 2 negotiation/utility ones do not.
        wired = [o for o in permit_offers if o.permit_offer_details.building_kind_id]
        self.assertEqual(len(wired), 7)
        for offer in wired:
            self.assertIsNotNone(
                offer.permit_offer_details.building_kind_id,
                f"Offer {offer.label!r} has no building_kind wired",
            )

    def test_total_offer_count_is_nine(self) -> None:
        role = ensure_builders_guild_clerk_role()
        offers = NPCServiceOffer.objects.filter(role=role)
        self.assertEqual(offers.count(), 9)

    def test_cottage_offer_capped_at_size_2(self) -> None:
        role = ensure_builders_guild_clerk_role()
        offer = NPCServiceOffer.objects.get(role=role, label="Apply for a Cottage permit")
        self.assertEqual(offer.permit_offer_details.default_max_target_size, 2)
        self.assertEqual(offer.permit_offer_details.building_kind.name, "Cottage")

    def test_guild_hall_offer_capped_at_size_6(self) -> None:
        role = ensure_builders_guild_clerk_role()
        offer = NPCServiceOffer.objects.get(role=role, label="Apply for a Guild Hall permit")
        self.assertEqual(offer.permit_offer_details.default_max_target_size, 6)
        self.assertEqual(offer.permit_offer_details.building_kind.name, "Guild Hall")

    def test_old_label_offers_cleaned_up(self) -> None:
        """Old-label offers from the previous seed are deleted on re-seed."""
        role = ensure_builders_guild_clerk_role()
        # Manually add an old-label offer to simulate pre-migration state
        NPCServiceOffer.objects.create(
            role=role,
            label="Apply for a small residential permit",
            kind=OfferKind.PERMIT,
        )
        # Re-seed — should clean up the old-label offer
        ensure_builders_guild_clerk_role()
        self.assertFalse(
            NPCServiceOffer.objects.filter(
                role=role, label="Apply for a small residential permit"
            ).exists()
        )

    def test_non_permit_offers_preserved(self) -> None:
        role = ensure_builders_guild_clerk_role()
        for label in (
            "Negotiate a discount on permit fees",
            "Request expedited processing",
        ):
            self.assertTrue(
                NPCServiceOffer.objects.filter(role=role, label=label).exists(),
                f"Non-permit offer {label!r} should still exist",
            )
