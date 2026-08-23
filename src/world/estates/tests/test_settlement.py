"""``execute_settlement`` journeys: debts-first, fall-throughs, sweep, claims (#1985)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import PosthumousJournalDisposition
from world.currency.constants import ContractFormality, ContractStatus
from world.currency.models import Business, Contract, ContractTerm
from world.currency.services import get_or_create_purse, get_or_create_treasury
from world.estates.constants import BequestKind, SettlementDoor, SettlementStatus
from world.estates.factories import BequestFactory, WillFactory
from world.estates.models import EstateClaim
from world.estates.services import execute_settlement, open_settlement
from world.items.constants import OwnershipEventType
from world.items.factories import ItemInstanceFactory
from world.items.models import OwnershipEvent
from world.journals.constants import PosthumousOverride
from world.journals.factories import JournalEntryFactory
from world.journals.models import JournalBequestGrant
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.factories import OrganizationFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory


def _dead_sheet():
    sheet = CharacterSheetFactory()
    CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
    return sheet


def _living_persona():
    sheet = CharacterSheetFactory()
    CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.ALIVE)
    return sheet.primary_persona


def _fund(sheet, coppers):
    purse = get_or_create_purse(sheet)
    purse.balance = coppers
    purse.save(update_fields=["balance"])
    return purse


class TestateJourneyTests(TestCase):
    def setUp(self):
        self.sheet = _dead_sheet()
        self.friend = _living_persona()
        self.spouse = _living_persona()
        self.org = OrganizationFactory()
        self.will = WillFactory(character_sheet=self.sheet)
        self.sword = ItemInstanceFactory(holder_character_sheet=self.sheet)
        self.ring = ItemInstanceFactory(holder_character_sheet=self.sheet)
        _fund(self.sheet, 1000)
        BequestFactory(
            will=self.will,
            kind=BequestKind.SPECIFIC_ITEM,
            item=self.sword,
            recipient_persona=self.friend,
        )
        BequestFactory(
            will=self.will,
            kind=BequestKind.COIN_AMOUNT,
            amount=500,
            recipient_persona=None,
            recipient_organization=self.org,
        )
        BequestFactory(will=self.will, kind=BequestKind.RESIDUARY, recipient_persona=self.spouse)
        # A notarized debt of 200 the deceased owes.
        self.creditor = _living_persona()
        contract = Contract.objects.create(
            proposer_persona=self.sheet.primary_persona,
            counterparty_persona=self.creditor,
            title="Loan",
            terms="PLACEHOLDER",
            formality=ContractFormality.NOTARIZED,
            status=ContractStatus.ACTIVE,
        )
        self.debt_term = ContractTerm.objects.create(
            contract=contract, payer_is_proposer=True, amount=200
        )
        open_settlement(self.sheet)

    def test_full_journey_debts_then_bequests_then_sweep(self):
        settlement = execute_settlement(self.sheet, via=SettlementDoor.READING)
        self.assertEqual(settlement.status, SettlementStatus.SETTLED)
        self.assertEqual(settlement.settled_via, SettlementDoor.READING)

        self.debt_term.refresh_from_db()
        self.assertTrue(self.debt_term.fulfilled)
        self.assertEqual(get_or_create_purse(self.creditor.character_sheet).balance, 200)

        self.sword.refresh_from_db()
        self.assertEqual(self.sword.holder_character_sheet, self.friend.character_sheet)
        self.assertTrue(
            OwnershipEvent.objects.filter(
                item_instance=self.sword, event_type=OwnershipEventType.INHERITED
            ).exists()
        )
        self.assertEqual(get_or_create_treasury(self.org).balance, 500)

        self.ring.refresh_from_db()
        self.assertEqual(self.ring.holder_character_sheet, self.spouse.character_sheet)
        self.assertEqual(get_or_create_purse(self.spouse.character_sheet).balance, 300)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 0)

    def test_first_door_wins(self):
        execute_settlement(self.sheet, via=SettlementDoor.FUNERAL)
        settlement = execute_settlement(self.sheet, via=SettlementDoor.READING)
        self.assertEqual(settlement.settled_via, SettlementDoor.FUNERAL)
        # No double delivery: org treasury credited exactly once.
        self.assertEqual(get_or_create_treasury(self.org).balance, 500)

    def test_dry_purse_partial_debt_starves_coin_bequests(self):
        _fund(self.sheet, 100)
        execute_settlement(self.sheet, via=SettlementDoor.AUTO)
        self.debt_term.refresh_from_db()
        self.assertFalse(self.debt_term.fulfilled)
        self.assertEqual(get_or_create_purse(self.creditor.character_sheet).balance, 100)
        self.assertEqual(get_or_create_treasury(self.org).balance, 0)

    def test_dead_recipient_falls_through_to_residuary(self):
        dead_recipient_sheet = _dead_sheet()
        self.sword.refresh_from_db()
        bequest = self.will.bequests.get(kind=BequestKind.SPECIFIC_ITEM)
        bequest.recipient_persona = dead_recipient_sheet.primary_persona
        bequest.save(update_fields=["recipient_persona"])
        execute_settlement(self.sheet, via=SettlementDoor.READING)
        self.sword.refresh_from_db()
        self.assertEqual(self.sword.holder_character_sheet, self.spouse.character_sheet)

    def test_adeemed_stolen_item_claims_to_named_recipient(self):
        thief = CharacterSheetFactory()
        OwnershipEvent.objects.create(
            item_instance=self.sword,
            event_type=OwnershipEventType.STOLEN,
            from_character_sheet=self.sheet,
            to_character_sheet=thief,
        )
        self.sword.holder_character_sheet = thief
        self.sword.save(update_fields=["holder_character_sheet"])
        execute_settlement(self.sheet, via=SettlementDoor.READING)
        self.sword.refresh_from_db()
        self.assertEqual(self.sword.holder_character_sheet, thief)  # never yanked back
        claim = EstateClaim.objects.get(item=self.sword)
        self.assertEqual(claim.claimant_persona, self.friend)

    def test_hot_bequest_to_consent_off_recipient_falls_through(self):
        # Make the sword hot (stolen FROM someone else, held by the deceased).
        victim = CharacterSheetFactory()
        OwnershipEvent.objects.create(
            item_instance=self.sword,
            event_type=OwnershipEventType.STOLEN,
            from_character_sheet=victim,
            to_character_sheet=self.sheet,
        )
        # The named friend has a live tenure -> consent-protected, default-deny.
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.friend.character_sheet),
            end_date=None,
        )
        execute_settlement(self.sheet, via=SettlementDoor.READING)
        self.sword.refresh_from_db()
        # Spouse (residuary heir, no tenure -> NPC-like, unprotected) receives instead.
        self.assertEqual(self.sword.holder_character_sheet, self.spouse.character_sheet)


class IntestateJourneyTests(TestCase):
    def test_no_will_no_kin_no_domain_parks_with_zero_mutations(self):
        sheet = _dead_sheet()
        ItemInstanceFactory(holder_character_sheet=sheet)
        _fund(sheet, 400)
        open_settlement(sheet)
        settlement = execute_settlement(sheet, via=SettlementDoor.AUTO)
        self.assertEqual(settlement.status, SettlementStatus.PARKED)
        self.assertEqual(get_or_create_purse(sheet).balance, 400)
        self.assertFalse(
            OwnershipEvent.objects.filter(
                event_type=OwnershipEventType.INHERITED, from_character_sheet=sheet
            ).exists()
        )

    def test_no_assets_no_heir_settles_trivially(self):
        sheet = _dead_sheet()
        open_settlement(sheet)
        settlement = execute_settlement(sheet, via=SettlementDoor.AUTO)
        self.assertEqual(settlement.status, SettlementStatus.SETTLED)

    def test_contract_substitution_seats_the_heir(self):
        sheet = _dead_sheet()
        heir = _living_persona()
        will = WillFactory(character_sheet=sheet)
        BequestFactory(will=will, kind=BequestKind.RESIDUARY, recipient_persona=heir)
        debtor = _living_persona()
        contract = Contract.objects.create(
            proposer_persona=debtor,
            counterparty_persona=sheet.primary_persona,
            title="Owed to the deceased",
            terms="PLACEHOLDER",
            formality=ContractFormality.NOTARIZED,
            status=ContractStatus.ACTIVE,
        )
        ContractTerm.objects.create(contract=contract, payer_is_proposer=True, amount=999)
        open_settlement(sheet)
        execute_settlement(sheet, via=SettlementDoor.READING)
        contract.refresh_from_db()
        self.assertEqual(contract.counterparty_persona, heir)
        self.assertEqual(contract.status, ContractStatus.ACTIVE)

    def test_business_winds_down_without_persona_heir(self):
        sheet = _dead_sheet()
        business = Business.objects.create(
            owner_persona=sheet.primary_persona, name="Dead Man's Forge"
        )
        org = OrganizationFactory()
        will = WillFactory(character_sheet=sheet)
        BequestFactory(
            will=will,
            kind=BequestKind.RESIDUARY,
            recipient_persona=None,
            recipient_organization=org,
        )
        open_settlement(sheet)
        settlement = execute_settlement(sheet, via=SettlementDoor.FUNERAL)
        self.assertEqual(settlement.status, SettlementStatus.SETTLED)
        business.refresh_from_db()
        self.assertFalse(business.active)

    def test_org_heir_items_become_free_loot(self):
        sheet = _dead_sheet()
        item = ItemInstanceFactory(holder_character_sheet=sheet)
        org = OrganizationFactory()
        will = WillFactory(character_sheet=sheet)
        BequestFactory(
            will=will,
            kind=BequestKind.RESIDUARY,
            recipient_persona=None,
            recipient_organization=org,
        )
        _fund(sheet, 250)
        open_settlement(sheet)
        execute_settlement(sheet, via=SettlementDoor.AUTO)
        item.refresh_from_db()
        self.assertIsNone(item.holder_character_sheet)
        self.assertEqual(get_or_create_treasury(org).balance, 250)


class JournalAfterlifeSettlementTests(TestCase):
    """The black-journal afterlife riding execute_settlement (#3287): the three
    dispositions plus a WRITINGS bequest."""

    def test_reveal_disposition_stamps_private_entries(self):
        sheet = _dead_sheet()
        sheet.posthumous_journal_disposition = PosthumousJournalDisposition.REVEAL
        sheet.save(update_fields=["posthumous_journal_disposition"])
        entry = JournalEntryFactory(author=sheet, is_public=False)
        open_settlement(sheet)
        settlement = execute_settlement(sheet, via=SettlementDoor.AUTO)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.revealed_at)
        self.assertEqual(entry.revealed_by_settlement, settlement)
        self.assertFalse(entry.is_public)

    def test_seal_disposition_never_reveals(self):
        sheet = _dead_sheet()
        sheet.posthumous_journal_disposition = PosthumousJournalDisposition.SEAL
        sheet.save(update_fields=["posthumous_journal_disposition"])
        entry = JournalEntryFactory(author=sheet, is_public=False)
        open_settlement(sheet)
        execute_settlement(sheet, via=SettlementDoor.AUTO)
        entry.refresh_from_db()
        self.assertIsNone(entry.revealed_at)

    def test_per_entry_override_wins_over_sheet_default(self):
        sheet = _dead_sheet()
        sheet.posthumous_journal_disposition = PosthumousJournalDisposition.REVEAL
        sheet.save(update_fields=["posthumous_journal_disposition"])
        sealed_entry = JournalEntryFactory(
            author=sheet, is_public=False, posthumous_override=PosthumousOverride.SEAL
        )
        open_settlement(sheet)
        execute_settlement(sheet, via=SettlementDoor.AUTO)
        sealed_entry.refresh_from_db()
        self.assertIsNone(sealed_entry.revealed_at)

    def test_writings_bequest_grants_recipient_access(self):
        sheet = _dead_sheet()
        recipient = _living_persona()
        will = WillFactory(character_sheet=sheet)
        BequestFactory(
            will=will,
            kind=BequestKind.WRITINGS,
            recipient_persona=recipient,
        )
        BequestFactory(will=will, kind=BequestKind.RESIDUARY, recipient_persona=recipient)
        open_settlement(sheet)
        settlement = execute_settlement(sheet, via=SettlementDoor.AUTO)
        grant = JournalBequestGrant.objects.get(
            recipient_sheet=recipient.character_sheet, deceased_sheet=sheet
        )
        self.assertEqual(grant.created_by_settlement, settlement)

    def test_writings_bequest_falls_through_to_heir_when_recipient_invalid(self):
        sheet = _dead_sheet()
        dead_recipient = _dead_sheet()
        heir = _living_persona()
        will = WillFactory(character_sheet=sheet)
        BequestFactory(
            will=will,
            kind=BequestKind.WRITINGS,
            recipient_persona=dead_recipient.primary_persona,
        )
        BequestFactory(will=will, kind=BequestKind.RESIDUARY, recipient_persona=heir)
        open_settlement(sheet)
        execute_settlement(sheet, via=SettlementDoor.AUTO)
        self.assertFalse(
            JournalBequestGrant.objects.filter(
                recipient_sheet=dead_recipient, deceased_sheet=sheet
            ).exists()
        )
        self.assertTrue(
            JournalBequestGrant.objects.filter(
                recipient_sheet=heir.character_sheet, deceased_sheet=sheet
            ).exists()
        )

    def test_no_writings_bequest_no_grant(self):
        sheet = _dead_sheet()
        heir = _living_persona()
        will = WillFactory(character_sheet=sheet)
        BequestFactory(will=will, kind=BequestKind.RESIDUARY, recipient_persona=heir)
        open_settlement(sheet)
        execute_settlement(sheet, via=SettlementDoor.AUTO)
        self.assertFalse(JournalBequestGrant.objects.filter(deceased_sheet=sheet).exists())

    def test_reveal_runs_even_with_no_will_at_all(self):
        """Decision 2 — reveal has no bequest of its own; it always runs at settlement."""
        sheet = _dead_sheet()
        sheet.posthumous_journal_disposition = PosthumousJournalDisposition.REVEAL
        sheet.save(update_fields=["posthumous_journal_disposition"])
        entry = JournalEntryFactory(author=sheet, is_public=False)
        open_settlement(sheet)
        execute_settlement(sheet, via=SettlementDoor.AUTO)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.revealed_at)
