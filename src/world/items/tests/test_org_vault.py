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


class VaultTransitTests(TestCase):
    """The collection return leg (#2540 ruling): deposit completes; embezzlement is gated."""

    def setUp(self) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.consent.constants import ConsentMode
        from world.consent.factories import SocialConsentCategoryFactory
        from world.items.org_vault_models import OrgVaultEvent, VaultTransit
        from world.items.services.org_vault import get_or_create_org_vault
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        self.org = OrganizationFactory()
        self.carrier = PersonaFactory()
        self.head = PersonaFactory()
        OrganizationMembershipFactory(persona=self.carrier, organization=self.org, rank=3)
        OrganizationMembershipFactory(persona=self.head, organization=self.org, rank=1)
        self.vault = get_or_create_org_vault(self.org)
        self.stones = [
            ItemInstanceFactory(holder_character_sheet=self.carrier.character_sheet)
            for _ in range(3)
        ]
        for stone in self.stones:
            VaultTransit.objects.create(
                vault=self.vault,
                item_instance=stone,
                carrier_character_sheet=self.carrier.character_sheet,
            )
        # Tenures so the consent gate can resolve both sides.
        for persona in (self.carrier, self.head):
            entry = RosterEntryFactory(character_sheet=persona.character_sheet)
            RosterTenureFactory(roster_entry=entry)
        self._account_factory = AccountFactory
        self._category_factory = SocialConsentCategoryFactory
        self._consent_modes = ConsentMode
        self._events = OrgVaultEvent
        self._transits = VaultTransit

    def _pilot(self, persona) -> None:
        character = persona.character_sheet.character
        character.db_account = self._account_factory()
        character.save(update_fields=["db_account"])

    def _seed_embezzlement(self, mode):
        return self._category_factory(key="embezzlement", default_mode=mode)

    def _rule_for(self, persona, category, mode) -> None:
        """Attach a per-tenure embezzlement rule (overrides the category default)."""
        from world.consent.factories import (
            SocialConsentCategoryRuleFactory,
            SocialConsentPreferenceFactory,
        )

        tenure = persona.character_sheet.roster_entry.current_tenure
        preference = SocialConsentPreferenceFactory(tenure=tenure)
        SocialConsentCategoryRuleFactory(preference=preference, category=category, mode=mode)

    def _resolve(self, keep=()):
        from world.items.services.org_vault import resolve_vault_transit

        return resolve_vault_transit(
            organization=self.org, carrier_persona=self.carrier, keep_item_ids=keep
        )

    def test_deposit_all_converts_custody_and_audits(self) -> None:
        resolved = self._resolve()
        self.assertEqual(len(resolved), 3)
        self.assertEqual(VaultHolding.objects.filter(vault=self.vault).count(), 3)
        for stone in self.stones:
            stone.refresh_from_db()
            self.assertIsNone(stone.holder_character_sheet)
        self.assertEqual(
            self._events.objects.filter(
                kind=OrgVaultEventKind.DEPOSIT, reason="collection deposit"
            ).count(),
            3,
        )
        self.assertFalse(self._transits.objects.filter(resolved_at__isnull=True).exists())

    def test_npc_carrier_never_skims(self) -> None:
        self._seed_embezzlement(self._consent_modes.EVERYONE)
        with self.assertRaises(ValidationError):  # unpiloted carrier has no opt-in path
            self._resolve(keep=[self.stones[0].pk])

    def test_keep_blocked_when_deciding_authority_blocks(self) -> None:
        self._pilot(self.carrier)
        self._pilot(self.head)
        self._seed_embezzlement(self._consent_modes.ALLOWLIST)  # nobody allowed by default
        with self.assertRaises(ValidationError):
            self._resolve(keep=[self.stones[0].pk])

    def test_npc_head_defers_to_next_piloted_authority(self) -> None:
        # Unpiloted head; a piloted tier-2 Voice below has opted out — blocked.
        self._pilot(self.carrier)
        voice = PersonaFactory()
        OrganizationMembershipFactory(persona=voice, organization=self.org, rank=2)
        self._pilot(voice)
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=voice.character_sheet))
        category = self._seed_embezzlement(self._consent_modes.EVERYONE)
        self._rule_for(voice, category, self._consent_modes.ALLOWLIST)  # the Voice opts out
        with self.assertRaises(ValidationError):
            self._resolve(keep=[self.stones[0].pk])

    def test_piloted_head_shields_opted_out_subordinates(self) -> None:
        # Piloted story-NPC head allows; the opted-out tier-3 carrier peer below is
        # never consulted — the highest active piloted member answers for the house.
        self._pilot(self.carrier)
        self._pilot(self.head)
        assistant = PersonaFactory()
        OrganizationMembershipFactory(persona=assistant, organization=self.org, rank=4)
        self._pilot(assistant)
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=assistant.character_sheet)
        )
        category = self._seed_embezzlement(self._consent_modes.EVERYONE)
        self._rule_for(assistant, category, self._consent_modes.ALLOWLIST)  # opted out, below
        resolved = self._resolve(keep=[self.stones[0].pk])
        self.assertEqual(len(resolved), 3)  # allowed — the assistant never had to engage

    def test_carrier_as_topmost_piloted_self_deals(self) -> None:
        # Unpiloted head, no other piloted members: the carrier IS the highest playable
        # authority — nobody unwilling is in the loop, the skim is their own story.
        self._pilot(self.carrier)
        self._seed_embezzlement(self._consent_modes.ALLOWLIST)  # mode irrelevant — no authority
        resolved = self._resolve(keep=[self.stones[0].pk])
        self.assertEqual(len(resolved), 3)

    def test_keep_resolves_kept_with_no_vault_event(self) -> None:
        self._pilot(self.carrier)
        self._pilot(self.head)
        self._seed_embezzlement(self._consent_modes.EVERYONE)
        kept_stone = self.stones[0]
        self._resolve(keep=[kept_stone.pk])
        kept_stone.refresh_from_db()
        self.assertEqual(  # the skimmed stone stays in the carrier's hands
            kept_stone.holder_character_sheet, self.carrier.character_sheet
        )
        self.assertEqual(VaultHolding.objects.filter(vault=self.vault).count(), 2)
        # The crime books no vault event — only the two honest deposits appear.
        self.assertEqual(self._events.objects.count(), 2)
        kept_row = self._transits.objects.get(item_instance=kept_stone)
        self.assertEqual(kept_row.resolution, "kept")  # the staff-side record
