"""Bank actions (#2540 Layer 4): the WHERE gate on org-vault deposit/withdraw/treasury.

REST-shape dispatches (plain int kwargs) against the audited vault/treasury services;
the only new logic under test is the BANK room-feature gate (and, for the treasury
action, the amount-kwarg coercion).
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.org_vault import (
    DeliverCollectionAction,
    TreasuryWithdrawAction,
    VaultDepositAction,
    VaultWithdrawAction,
)
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import SocialConsentCategoryFactory
from world.currency.services import get_or_create_purse, get_or_create_treasury
from world.items.factories import ItemInstanceFactory
from world.items.org_vault_models import VaultHolding, VaultTransit
from world.items.services.org_vault import get_or_create_org_vault
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class BankActionTests(TestCase):
    def setUp(self) -> None:
        self.org = OrganizationFactory(name="House Coffers")
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        OrganizationMembershipFactory(
            organization=self.org, persona=self.sheet.primary_persona, rank=1
        )
        self.room_profile = RoomProfileFactory()
        self.character.location = self.room_profile.objectdb
        self.item = ItemInstanceFactory(holder_character_sheet=self.sheet)

    def _install_bank(self) -> None:
        kind = RoomFeatureKindFactory(
            name="Bank Access", service_strategy=RoomFeatureServiceStrategy.BANK
        )
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=kind, level=1)

    def test_deposit_refused_without_bank_access(self) -> None:
        result = VaultDepositAction().run(
            actor=self.character, organization_id=self.org.pk, item_instance_id=self.item.pk
        )
        self.assertFalse(result.success)
        self.assertFalse(VaultHolding.objects.exists())

    def test_deposit_and_withdraw_at_a_bank(self) -> None:
        self._install_bank()
        result = VaultDepositAction().run(
            actor=self.character, organization_id=self.org.pk, item_instance_id=self.item.pk
        )
        self.assertTrue(result.success, result.message)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.holder_character_sheet)  # org custody
        result = VaultWithdrawAction().run(
            actor=self.character, organization_id=self.org.pk, item_instance_id=self.item.pk
        )
        self.assertTrue(result.success, result.message)
        self.item.refresh_from_db()
        self.assertEqual(self.item.holder_character_sheet, self.sheet)

    def test_service_rejections_surface_as_failures(self) -> None:
        self._install_bank()
        stranger_item = ItemInstanceFactory()  # not held by the actor
        result = VaultDepositAction().run(
            actor=self.character, organization_id=self.org.pk, item_instance_id=stranger_item.pk
        )
        self.assertFalse(result.success)


class TreasuryWithdrawActionTests(TestCase):
    def setUp(self) -> None:
        self.org = OrganizationFactory(name="House Coffers")
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        OrganizationMembershipFactory(
            organization=self.org, persona=self.sheet.primary_persona, rank=1
        )
        self.room_profile = RoomProfileFactory()
        self.character.location = self.room_profile.objectdb
        self.treasury = get_or_create_treasury(self.org)
        self.treasury.balance = 1000
        self.treasury.save(update_fields=["balance"])

    def _install_bank(self) -> None:
        kind = RoomFeatureKindFactory(
            name="Bank Access", service_strategy=RoomFeatureServiceStrategy.BANK
        )
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=kind, level=1)

    def test_withdraw_refused_without_bank_access(self) -> None:
        result = TreasuryWithdrawAction().run(
            actor=self.character, organization_id=self.org.pk, amount=300
        )
        self.assertFalse(result.success)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)

    def test_rank_gated_success_moves_coppers_treasury_to_purse(self) -> None:
        self._install_bank()
        result = TreasuryWithdrawAction().run(
            actor=self.character, organization_id=self.org.pk, amount=300
        )
        self.assertTrue(result.success, result.message)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 700)
        purse = get_or_create_purse(self.sheet)
        self.assertEqual(purse.balance, 300)

    def test_below_rank_member_cannot_withdraw(self) -> None:
        self._install_bank()
        grunt_sheet = CharacterSheetFactory()
        grunt = grunt_sheet.character
        grunt.location = self.room_profile.objectdb
        OrganizationMembershipFactory(
            organization=self.org, persona=grunt_sheet.primary_persona, rank=5
        )
        result = TreasuryWithdrawAction().run(actor=grunt, organization_id=self.org.pk, amount=100)
        self.assertFalse(result.success)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)

    def test_amount_exceeding_treasury_fails_cleanly(self) -> None:
        self._install_bank()
        result = TreasuryWithdrawAction().run(
            actor=self.character, organization_id=self.org.pk, amount=5000
        )
        self.assertFalse(result.success)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)

    def test_invalid_amounts_fail_without_touching_the_treasury(self) -> None:
        self._install_bank()
        for bad_amount in (0, -5, "abc"):
            with self.subTest(bad_amount=bad_amount):
                result = TreasuryWithdrawAction().run(
                    actor=self.character, organization_id=self.org.pk, amount=bad_amount
                )
                self.assertFalse(result.success)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)

    def test_missing_amount_fails_without_touching_the_treasury(self) -> None:
        self._install_bank()
        result = TreasuryWithdrawAction().run(actor=self.character, organization_id=self.org.pk)
        self.assertFalse(result.success)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)


class DeliverCollectionActionTests(TestCase):
    """The collection return leg (#2540): deposit-all + the embezzlement opt-in."""

    def setUp(self) -> None:
        self.org = OrganizationFactory(name="House Coffers")
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.db_account = AccountFactory()  # a piloted carrier
        self.character.save(update_fields=["db_account"])
        OrganizationMembershipFactory(
            organization=self.org, persona=self.sheet.primary_persona, rank=3
        )
        self.room_profile = RoomProfileFactory()
        self.character.location = self.room_profile.objectdb
        self.vault = get_or_create_org_vault(self.org)

    def _install_bank(self) -> None:
        kind = RoomFeatureKindFactory(
            name="Bank Access", service_strategy=RoomFeatureServiceStrategy.BANK
        )
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=kind, level=1)

    def _open_transit(self):
        stone = ItemInstanceFactory(holder_character_sheet=self.sheet)
        VaultTransit.objects.create(
            vault=self.vault, item_instance=stone, carrier_character_sheet=self.sheet
        )
        return stone

    def test_refused_without_bank_access(self) -> None:
        self._open_transit()
        result = DeliverCollectionAction().run(actor=self.character, organization_id=self.org.pk)
        self.assertFalse(result.success)
        self.assertFalse(VaultHolding.objects.exists())

    def test_no_open_transits_fails_cleanly(self) -> None:
        self._install_bank()
        result = DeliverCollectionAction().run(actor=self.character, organization_id=self.org.pk)
        self.assertFalse(result.success)
        self.assertIn("nothing owed", result.message)

    def test_delivers_all_open_transits(self) -> None:
        self._install_bank()
        self._open_transit()
        self._open_transit()
        result = DeliverCollectionAction().run(actor=self.character, organization_id=self.org.pk)
        self.assertTrue(result.success, result.message)
        self.assertEqual(VaultHolding.objects.filter(vault=self.vault).count(), 2)
        self.assertFalse(VaultTransit.objects.filter(resolved_at__isnull=True).exists())
        self.assertNotIn("PLACEHOLDER", result.message)

    def test_keep_without_consent_authority_refuses_and_leaves_transits_open(self) -> None:
        self._install_bank()
        stone = self._open_transit()
        # No embezzlement SocialConsentCategory seeded -> can_embezzle_from refuses
        # (the double-gate's "unseeded resolves strict" fallback).
        result = DeliverCollectionAction().run(
            actor=self.character, organization_id=self.org.pk, keep_item_ids=[stone.pk]
        )
        self.assertFalse(result.success)
        self.assertFalse(VaultHolding.objects.exists())
        self.assertTrue(
            VaultTransit.objects.filter(item_instance=stone, resolved_at__isnull=True).exists()
        )

    def test_keep_with_consent_authority_kept_and_flagged_neutrally(self) -> None:
        self._install_bank()
        stone = self._open_transit()
        other_stone = self._open_transit()
        # The carrier is the org's sole active member -> the topmost piloted
        # stakeholder -> self-dealing is allowed regardless of consent mode.
        SocialConsentCategoryFactory(key="embezzlement", default_mode=ConsentMode.ALLOWLIST)
        result = DeliverCollectionAction().run(
            actor=self.character,
            organization_id=self.org.pk,
            keep_item_ids=[stone.pk],
        )
        self.assertTrue(result.success, result.message)
        self.assertIn("PLACEHOLDER", result.message)
        stone.refresh_from_db()
        self.assertEqual(stone.holder_character_sheet, self.sheet)  # kept, not vaulted
        other_stone.refresh_from_db()
        self.assertIsNone(other_stone.holder_character_sheet)  # honestly deposited
        self.assertEqual(VaultHolding.objects.filter(vault=self.vault).count(), 1)

    def test_keep_item_ids_naming_a_foreign_item_fails_cleanly(self) -> None:
        self._install_bank()
        stone = self._open_transit()
        foreign_item = ItemInstanceFactory()  # not an open transit for this carrier/org
        result = DeliverCollectionAction().run(
            actor=self.character,
            organization_id=self.org.pk,
            keep_item_ids=[foreign_item.pk],
        )
        self.assertFalse(result.success)
        self.assertFalse(VaultHolding.objects.exists())
        self.assertTrue(
            VaultTransit.objects.filter(item_instance=stone, resolved_at__isnull=True).exists()
        )
