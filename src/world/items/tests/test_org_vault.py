"""Org-vault custody (#2540 Layer 4): deposit/withdraw services, authority, audit."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.items.constants import OrgVaultEventKind
from world.items.factories import ItemInstanceFactory
from world.items.org_vault_models import OrgVaultEvent, VaultHolding
from world.items.services.org_vault import (
    can_access_vault,
    deposit_item_to_vault,
    get_or_create_org_vault,
    withdraw_item_from_vault,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class OrgVaultServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.head = PersonaFactory()
        cls.grunt = PersonaFactory()
        cls.outsider = PersonaFactory()
        OrganizationMembershipFactory(persona=cls.head, organization=cls.org, rank=1)
        OrganizationMembershipFactory(persona=cls.grunt, organization=cls.org, rank=5)

    def _held_item(self, persona):
        return ItemInstanceFactory(holder_character_sheet=persona.character_sheet)

    def test_any_member_deposits_and_custody_moves_to_the_org(self) -> None:
        item = self._held_item(self.grunt)
        holding = deposit_item_to_vault(
            organization=self.org, persona=self.grunt, item_instance=item
        )
        item.refresh_from_db()
        self.assertIsNone(item.holder_character_sheet)  # custody is the org's now
        self.assertEqual(holding.deposited_by, self.grunt)
        event = OrgVaultEvent.objects.get(kind=OrgVaultEventKind.DEPOSIT)
        self.assertEqual(event.actor_persona, self.grunt)

    def test_outsider_cannot_deposit(self) -> None:
        item = self._held_item(self.outsider)
        with self.assertRaises(ValidationError):
            deposit_item_to_vault(organization=self.org, persona=self.outsider, item_instance=item)

    def test_cannot_deposit_an_item_you_do_not_hold(self) -> None:
        item = self._held_item(self.head)
        with self.assertRaises(ValidationError):
            deposit_item_to_vault(organization=self.org, persona=self.grunt, item_instance=item)

    def test_withdraw_is_rank_gated(self) -> None:
        item = self._held_item(self.grunt)
        deposit_item_to_vault(organization=self.org, persona=self.grunt, item_instance=item)
        vault = get_or_create_org_vault(self.org)
        self.assertTrue(can_access_vault(vault, self.head))
        self.assertFalse(can_access_vault(vault, self.grunt))  # tier 5 > withdraw_rank_max 1
        with self.assertRaises(ValidationError):
            withdraw_item_from_vault(organization=self.org, persona=self.grunt, item_instance=item)

    def test_authorized_withdraw_returns_custody_and_audits(self) -> None:
        item = self._held_item(self.grunt)
        deposit_item_to_vault(organization=self.org, persona=self.grunt, item_instance=item)
        withdrawn = withdraw_item_from_vault(
            organization=self.org, persona=self.head, item_instance=item
        )
        self.assertEqual(withdrawn.holder_character_sheet, self.head.character_sheet)
        self.assertFalse(VaultHolding.objects.exists())
        self.assertTrue(
            OrgVaultEvent.objects.filter(
                kind=OrgVaultEventKind.WITHDRAW, actor_persona=self.head
            ).exists()
        )

    def test_withdraw_can_direct_to_another_persona(self) -> None:
        item = self._held_item(self.grunt)
        deposit_item_to_vault(organization=self.org, persona=self.grunt, item_instance=item)
        withdrawn = withdraw_item_from_vault(
            organization=self.org,
            persona=self.head,
            item_instance=item,
            to_persona=self.outsider,  # the VAULT_ITEM boon shape
        )
        self.assertEqual(withdrawn.holder_character_sheet, self.outsider.character_sheet)

    def test_double_deposit_rejected(self) -> None:
        item = self._held_item(self.grunt)
        deposit_item_to_vault(organization=self.org, persona=self.grunt, item_instance=item)
        # No longer held by the grunt, and already vaulted — both gates reject it.
        with self.assertRaises(ValidationError):
            deposit_item_to_vault(organization=self.org, persona=self.grunt, item_instance=item)
