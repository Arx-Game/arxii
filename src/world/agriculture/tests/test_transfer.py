"""Tests for inter-domain food transfer (#2219)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.domains import TransferFoodAction
from world.agriculture.models import FoodStockpile, FoodTransfer
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.services import create_domain


def _patch_capacity(return_value: int = 10000):
    """Context-manager patch for max_food_capacity (no Granaries in test DB)."""
    return patch(
        "world.agriculture.services.transfer.max_food_capacity",
        return_value=return_value,
    )


class TransferFoodActionTests(TestCase):
    """Journey tests for the TransferFoodAction dispatch seam."""

    def setUp(self) -> None:
        patcher = _patch_capacity(10000)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.org = OrganizationFactory(name="House Westrock")
        self.source_domain = create_domain(
            area=AreaFactory(), name="Westrock Vale", owner_org=self.org
        )
        self.target_domain = create_domain(
            area=AreaFactory(), name="Eastrock Vale", owner_org=self.org
        )
        self.source_stockpile = FoodStockpile.objects.create(domain=self.source_domain, stored=500)
        self.target_stockpile = FoodStockpile.objects.create(domain=self.target_domain, stored=50)
        # Leader — a can_manage_ranks (tier 1) membership for the actor's persona.
        self.leader_sheet = CharacterSheetFactory()
        self.leader = self.leader_sheet.character
        OrganizationMembershipFactory(
            organization=self.org, persona=self.leader_sheet.primary_persona, rank=1
        )
        # Outsider — no membership, no office.
        self.outsider_sheet = CharacterSheetFactory()
        self.outsider = self.outsider_sheet.character

    def test_successful_transfer(self) -> None:
        result = TransferFoodAction().run(
            actor=self.leader,
            source_domain_id=self.source_domain.pk,
            target_domain_id=self.target_domain.pk,
            amount=100,
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.data["landed"], 100)
        self.assertEqual(result.data["overflow"], 0)
        self.source_stockpile.refresh_from_db()
        self.target_stockpile.refresh_from_db()
        self.assertEqual(self.source_stockpile.stored, 400)
        self.assertEqual(self.target_stockpile.stored, 150)
        self.assertEqual(FoodTransfer.objects.count(), 1)
        ft = FoodTransfer.objects.first()
        self.assertEqual(ft.source_domain, self.source_domain)
        self.assertEqual(ft.target_domain, self.target_domain)
        self.assertEqual(ft.amount, 100)

    def test_unauthorized_persona_fails(self) -> None:
        result = TransferFoodAction().run(
            actor=self.outsider,
            source_domain_id=self.source_domain.pk,
            target_domain_id=self.target_domain.pk,
            amount=10,
        )
        self.assertFalse(result.success)
        self.assertIn("standing", result.message.lower())

    def test_same_source_and_target_fails(self) -> None:
        result = TransferFoodAction().run(
            actor=self.leader,
            source_domain_id=self.source_domain.pk,
            target_domain_id=self.source_domain.pk,
            amount=10,
        )
        self.assertFalse(result.success)

    def test_zero_amount_fails(self) -> None:
        result = TransferFoodAction().run(
            actor=self.leader,
            source_domain_id=self.source_domain.pk,
            target_domain_id=self.target_domain.pk,
            amount=0,
        )
        self.assertFalse(result.success)

    def test_insufficient_food_fails(self) -> None:
        result = TransferFoodAction().run(
            actor=self.leader,
            source_domain_id=self.source_domain.pk,
            target_domain_id=self.target_domain.pk,
            amount=10000,
        )
        self.assertFalse(result.success)

    def test_unknown_source_domain_fails(self) -> None:
        result = TransferFoodAction().run(
            actor=self.leader,
            source_domain_id=999999,
            target_domain_id=self.target_domain.pk,
            amount=10,
        )
        self.assertFalse(result.success)

    def test_unknown_target_domain_fails(self) -> None:
        result = TransferFoodAction().run(
            actor=self.leader,
            source_domain_id=self.source_domain.pk,
            target_domain_id=999999,
            amount=10,
        )
        self.assertFalse(result.success)


class TransferFoodServiceTests(TestCase):
    """Unit tests for the transfer_food() service function."""

    def setUp(self) -> None:
        patcher = _patch_capacity(10000)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.org = OrganizationFactory(name="House Test")
        self.source_domain = create_domain(
            area=AreaFactory(), name="Source Domain", owner_org=self.org
        )
        self.target_domain = create_domain(
            area=AreaFactory(), name="Target Domain", owner_org=self.org
        )
        self.source_stockpile = FoodStockpile.objects.create(domain=self.source_domain, stored=500)
        self.target_stockpile = FoodStockpile.objects.create(domain=self.target_domain, stored=50)

    def test_successful_transfer(self) -> None:
        from world.agriculture.services import transfer_food

        result = transfer_food(
            source_domain=self.source_domain,
            target_domain=self.target_domain,
            amount=100,
        )
        self.assertEqual(result.landed, 100)
        self.assertEqual(result.overflow, 0)
        self.assertFalse(result.cancelled)
        self.source_stockpile.refresh_from_db()
        self.target_stockpile.refresh_from_db()
        self.assertEqual(self.source_stockpile.stored, 400)
        self.assertEqual(self.target_stockpile.stored, 150)
        self.assertEqual(FoodTransfer.objects.count(), 1)

    def test_overflow_when_target_full(self) -> None:
        """Transfer exceeding target capacity loses the excess."""
        from world.agriculture.services import transfer_food

        # Patch capacity to 0 for this test — simulates no Granaries.
        with _patch_capacity(0):
            self.target_stockpile.stored = 0
            self.target_stockpile.save()
            result = transfer_food(
                source_domain=self.source_domain,
                target_domain=self.target_domain,
                amount=100,
            )
        self.assertEqual(result.landed, 0)
        self.assertEqual(result.overflow, 100)
        self.source_stockpile.refresh_from_db()
        self.assertEqual(self.source_stockpile.stored, 400)

    def test_insufficient_food_raises(self) -> None:
        from world.agriculture.services import transfer_food

        with self.assertRaises(ValueError):
            transfer_food(
                source_domain=self.source_domain,
                target_domain=self.target_domain,
                amount=1000,
            )

    def test_same_domain_raises(self) -> None:
        from world.agriculture.services import transfer_food

        with self.assertRaises(ValueError):
            transfer_food(
                source_domain=self.source_domain,
                target_domain=self.source_domain,
                amount=10,
            )

    def test_zero_amount_raises(self) -> None:
        from world.agriculture.services import transfer_food

        with self.assertRaises(ValueError):
            transfer_food(
                source_domain=self.source_domain,
                target_domain=self.target_domain,
                amount=0,
            )

    def test_source_without_stockpile_raises(self) -> None:
        """A source domain with no FoodStockpile row cannot send food."""
        from world.agriculture.services import transfer_food

        third_domain = create_domain(
            area=AreaFactory(), name="No Stockpile Domain", owner_org=self.org
        )
        with self.assertRaises(ValueError):
            transfer_food(
                source_domain=third_domain,
                target_domain=self.target_domain,
                amount=10,
            )

    def test_target_without_stockpile_is_created(self) -> None:
        """A target domain with no FoodStockpile gets one lazily (get_or_create)."""
        from world.agriculture.services import transfer_food

        target_no_stockpile = create_domain(
            area=AreaFactory(), name="No Target Stockpile", owner_org=self.org
        )
        transfer_food(
            source_domain=self.source_domain,
            target_domain=target_no_stockpile,
            amount=10,
        )
        self.assertTrue(FoodStockpile.objects.filter(domain=target_no_stockpile).exists())
