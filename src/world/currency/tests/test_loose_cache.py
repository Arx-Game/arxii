"""Loose coin caches (#1909): arbitrary-value physical money, fee-free."""

from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import ObjectDBFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import put_in, take_out
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.constants import Denomination
from world.currency.models import CurrencyInstrumentDetails
from world.currency.services import (
    get_or_create_purse,
    mint_loose_cache,
    redeem_instrument,
    transfer,
)
from world.items.constants import OwnershipEventType
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import OwnershipEvent


class LooseCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.purse = get_or_create_purse(cls.sheet)
        transfer(amount=1_000, reason="test seed", to_purse=cls.purse)

    def test_mint_loose_cache_conserves_value_no_fee(self):
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 650)  # exactly 350 left, zero fee
        details = CurrencyInstrumentDetails.objects.get(item_instance=instance)
        self.assertEqual(details.denomination, Denomination.LOOSE)
        self.assertEqual(details.face_value, 350)
        self.assertEqual(instance.holder_character_sheet, self.sheet)

    def test_mint_loose_cache_rejects_nonpositive_and_insufficient(self):
        with self.assertRaises(ValidationError):
            mint_loose_cache(amount=0, holder_sheet=self.sheet, from_purse=self.purse)
        with self.assertRaises(ValidationError):
            mint_loose_cache(amount=999_999, holder_sheet=self.sheet, from_purse=self.purse)

    def test_deposit_via_redeem_instrument_roundtrip(self):
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        redeem_instrument(instance=instance, to_purse=self.purse)
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 1_000)
        self.assertEqual(CurrencyInstrumentDetails.objects.count(), 0)  # instrument consumed


class LooseCachePhysicalTests(TestCase):
    """Minted coin is born physical (#1909 fix round): a real ObjectDB in inventory.

    Per-test setUp (not setUpTestData) — Evennia typeclass instances are not
    deepcopy-safe as class-level test data, and these tests walk
    ``sheet.character``.
    """

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.purse = get_or_create_purse(self.sheet)
        transfer(amount=1_000, reason="test seed", to_purse=self.purse)

    def test_minted_cache_has_game_object_in_minter_inventory(self):
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        self.assertIsNotNone(instance.game_object)
        self.assertEqual(instance.game_object.location, self.character)

    def test_minted_cache_put_in_then_take_out_roundtrip(self):
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        chest_template = ItemTemplateFactory(name="LooseCache Chest", is_container=True)
        chest_obj = ObjectDBFactory(db_key="LooseCacheChest", location=self.character)
        chest = ItemInstanceFactory(
            template=chest_template,
            game_object=chest_obj,
            holder_character_sheet=self.sheet,
        )
        ctx = MagicMock()
        character_state = CharacterState(self.character, context=ctx)
        cache_state = ItemState(instance, context=ctx)
        chest_state = ItemState(chest, context=ctx)

        put_in(character_state, cache_state, chest_state)
        instance.refresh_from_db()
        self.assertEqual(instance.contained_in, chest)
        self.assertEqual(instance.game_object.location, chest_obj)

        take_out(character_state, cache_state)
        instance.refresh_from_db()
        self.assertIsNone(instance.contained_in)
        self.assertEqual(instance.game_object.location, self.character)

    def test_redeem_consumes_the_physical_object(self):
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        game_object_pk = instance.game_object.pk
        redeem_instrument(instance=instance, to_purse=self.purse)
        self.assertFalse(ObjectDB.objects.filter(pk=game_object_pk).exists())
        self.assertEqual(CurrencyInstrumentDetails.objects.count(), 0)
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 1_000)

    def test_provenance_survives_redemption(self):
        """OwnershipEvent rows outlive the redeemed coin (#1025 provenance, SET_NULL).

        Pins the deletion-order/FK behavior the redeem path relies on: deleting
        the game_object CASCADE-removes the ItemInstance, and the event's
        ``item_instance`` FK nulls out while the from/to sheet audit trail stays
        intact.
        """
        giver_sheet = CharacterSheetFactory()
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        # Direct row creation matching the give service writer's shape
        # (flows.service_functions.inventory.give).
        event = OwnershipEvent.objects.create(
            item_instance=instance,
            event_type=OwnershipEventType.GIVEN,
            from_character_sheet=giver_sheet,
            to_character_sheet=self.sheet,
            from_persona_display=giver_sheet.primary_persona,
            to_persona_display=self.sheet.primary_persona,
        )

        redeem_instrument(instance=instance, to_purse=self.purse)

        # Read raw column values — SharedMemoryModel's identity map makes
        # refresh_from_db() a no-op (the re-fetch returns the same cached
        # instance; the loaddata-can't-update quirk, #946).
        row = (
            OwnershipEvent.objects.filter(pk=event.pk)
            .values(
                "item_instance_id",
                "event_type",
                "from_character_sheet_id",
                "to_character_sheet_id",
            )
            .get()
        )
        self.assertIsNone(row["item_instance_id"])  # SET_NULL, row not cascaded
        self.assertEqual(row["event_type"], OwnershipEventType.GIVEN)
        self.assertEqual(row["from_character_sheet_id"], giver_sheet.pk)
        self.assertEqual(row["to_character_sheet_id"], self.sheet.pk)
