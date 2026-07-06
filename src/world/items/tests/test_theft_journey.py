"""End-to-end theft journey (#1909 Task 7): withdraw -> stow -> steal -> deposit.

Exercises the spec's primary journey at the service seam, tying together three
task branches that only had isolated coverage before: physical currency
(``mint_loose_cache`` / ``redeem_instrument``), container access policy
(``OWNER_ONLY``), and the consent-gated ``steal`` bypass. A victim withdraws a
loose-coin cache, stows it in an owner-only chest, and a thief steals it —
permitted only because the victim opted in to being targeted for theft. A
second, non-consenting victim's item stays out of reach. Ledger conservation
(purse balances + outstanding instrument face values) holds at every step.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import put_in, steal, take_out
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.services import (
    set_social_consent_category_rule,
    set_social_consent_preference,
    theft_category,
)
from world.currency.constants import parse_coppers
from world.currency.models import CurrencyInstrumentDetails
from world.currency.services import (
    get_or_create_purse,
    mint_loose_cache,
    redeem_instrument,
    transfer,
)
from world.items.constants import ContainerAccessPolicy, OwnershipEventType
from world.items.exceptions import ContainerAccessDenied, TheftNotPermitted
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import OwnershipEvent
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.models import LegendEntry


class TheftJourneyTests(TestCase):
    """The spec's primary journey, service-seam end-to-end (#1909)."""

    def setUp(self) -> None:
        # Evennia typeclass instances cannot live on setUpTestData (DbHolder
        # deepcopy issue) — same per-test setUp pattern as test_steal_service.py.
        self.room = ObjectDBFactory(
            db_key="JourneyRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        self.victim = CharacterFactory(db_key="JourneyVictim", location=self.room)
        self.victim_sheet = CharacterSheetFactory(character=self.victim)
        self.victim_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.victim_sheet)
        )
        self.victim_purse = get_or_create_purse(self.victim_sheet)
        transfer(amount=1_000, reason="journey seed", to_purse=self.victim_purse)
        # The deliberate opt-in: EVERYONE may target this victim for theft.
        preference = set_social_consent_preference(self.victim_tenure, allow_social_actions=True)
        set_social_consent_category_rule(preference, theft_category(), ConsentMode.EVERYONE)

        self.thief = CharacterFactory(db_key="JourneyThief", location=self.room)
        self.thief_sheet = CharacterSheetFactory(character=self.thief)
        RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=self.thief_sheet))
        self.thief_purse = get_or_create_purse(self.thief_sheet)

        # A second, non-consenting victim: no category rule -> theft_category's
        # default_mode (ALLOWLIST, default-deny) blocks the thief.
        self.bystander = CharacterFactory(db_key="JourneyBystander", location=self.room)
        self.bystander_sheet = CharacterSheetFactory(character=self.bystander)
        RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=self.bystander_sheet))

        self.victim_state = CharacterState(self.victim, context=MagicMock())
        self.thief_state = CharacterState(self.thief, context=MagicMock())

    def _ledger_total(self) -> int:
        """Purse balances + every outstanding instrument's face value.

        Physical coin caches carry value *off* the ledger while they exist as
        items — this sum must stay constant across mint/steal/redeem.
        """
        self.victim_purse.refresh_from_db()
        self.thief_purse.refresh_from_db()
        outstanding = sum(CurrencyInstrumentDetails.objects.values_list("face_value", flat=True))
        return self.victim_purse.balance + self.thief_purse.balance + outstanding

    def test_withdraw_stow_steal_deposit_journey(self) -> None:
        total_before = self._ledger_total()

        # 1. Victim withdraws 3s5c as a physical loose-coin cache (no mint fee).
        amount = parse_coppers("3s 5c")
        self.assertEqual(amount, 35)
        cache = mint_loose_cache(
            amount=amount, holder_sheet=self.victim_sheet, from_purse=self.victim_purse
        )
        self.victim_purse.refresh_from_db()
        self.assertEqual(self.victim_purse.balance, 965)
        self.assertEqual(self._ledger_total(), total_before)

        # 2. Victim stows the cache in an owner-only chest sitting in the room.
        chest_template = ItemTemplateFactory(name="JourneyChest", is_container=True)
        chest_obj = ObjectDBFactory(db_key="JourneyChestObj", location=self.room)
        chest = ItemInstanceFactory(
            template=chest_template,
            game_object=chest_obj,
            holder_character_sheet=self.victim_sheet,
            access_policy=ContainerAccessPolicy.OWNER_ONLY,
        )
        ctx = MagicMock()
        cache_state = ItemState(cache, context=ctx)
        chest_state = ItemState(chest, context=ctx)
        put_in(self.victim_state, cache_state, chest_state)
        cache.refresh_from_db()
        self.assertEqual(cache.contained_in, chest)
        self.assertEqual(self._ledger_total(), total_before)

        # 3a. A third party's item is out of reach — the bystander never opted
        # in, so theft_category's default-deny blocks the thief outright.
        bystander_item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        bystander_item_obj.location = self.room
        bystander_item_obj.save()
        bystander_item = ItemInstanceFactory(
            game_object=bystander_item_obj, holder_character_sheet=self.bystander_sheet
        )
        bystander_item_state = ItemState(bystander_item, context=ctx)
        with self.assertRaises(TheftNotPermitted):
            steal(self.thief_state, bystander_item_state)
        self.assertFalse(OwnershipEvent.objects.filter(item_instance=bystander_item).exists())

        # 3b. Plain take-out of the cache from the OWNER_ONLY chest is refused —
        # ownership gates cannot be bypassed by a bare take.
        with self.assertRaises(ContainerAccessDenied):
            take_out(self.thief_state, cache_state)

        # 3c. Steal succeeds — the victim's EVERYONE rule permits it.
        steal(self.thief_state, cache_state)
        cache.refresh_from_db()
        cache.game_object.refresh_from_db()
        self.assertEqual(cache.holder_character_sheet, self.thief_sheet)
        self.assertEqual(cache.game_object.location, self.thief)
        self.assertIsNone(cache.contained_in)

        event = OwnershipEvent.objects.get(item_instance=cache)
        self.assertEqual(event.event_type, OwnershipEventType.STOLEN)
        self.assertEqual(event.from_character_sheet, self.victim_sheet)
        self.assertEqual(event.to_character_sheet, self.thief_sheet)

        thief_persona = self.thief_sheet.primary_persona
        deed = LegendEntry.objects.get(persona=thief_persona)
        crime_tag = deed.crime_tags.get()
        self.assertEqual(crime_tag.crime_kind.slug, "theft")

        self.assertEqual(self._ledger_total(), total_before)

        # 4. Thief deposits the stolen cache — redemption credits their purse
        # and consumes the physical instrument (never a lingering ghost object).
        cache_pk = cache.pk  # redeem deletes the row; keep the id for the check below.
        redeem_instrument(instance=cache, to_purse=self.thief_purse)
        self.thief_purse.refresh_from_db()
        self.assertEqual(self.thief_purse.balance, 35)
        self.assertFalse(
            CurrencyInstrumentDetails.objects.filter(item_instance_id=cache_pk).exists()
        )

        self.assertEqual(self._ledger_total(), total_before)
