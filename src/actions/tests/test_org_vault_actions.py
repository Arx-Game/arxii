"""Bank actions (#2540 Layer 4): the WHERE gate on org-vault deposit/withdraw.

REST-shape dispatches (plain int kwargs) against the audited vault services; the only
new logic under test is the BANK room-feature gate.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.org_vault import VaultDepositAction, VaultWithdrawAction
from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory
from world.items.org_vault_models import VaultHolding
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
