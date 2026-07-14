"""Hot-goods receipt consent gate on ``give`` (#1985).

A hot item (stolen, never returned to the victim) may only be given to a
recipient whose ``receiving-stolen-goods`` consent admits the giver. The
refusal is category-generic (``RecipientConsentDenied``) so the provenance
never leaks. NPC recipients (no live tenure) are unaffected.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import give
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.services import (
    add_social_consent_whitelist,
    receiving_stolen_goods_category,
    set_social_consent_category_rule,
    set_social_consent_preference,
)
from world.items.constants import OwnershipEventType
from world.items.exceptions import RecipientConsentDenied
from world.items.factories import ItemInstanceFactory
from world.items.models import OwnershipEvent
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class HotGoodsConsentGateTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="FenceRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.victim_sheet = CharacterSheetFactory()
        self.giver = CharacterFactory(db_key="Fence", location=self.room)
        self.giver_sheet = CharacterSheetFactory(character=self.giver)
        self.recipient = CharacterFactory(db_key="Buyer", location=self.room)
        self.recipient_sheet = CharacterSheetFactory(character=self.recipient)
        self.recipient_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.recipient_sheet),
            end_date=None,
        )
        self.giver_state = CharacterState(self.giver, context=MagicMock())
        self.recipient_state = CharacterState(self.recipient, context=MagicMock())

    def _held_item(self, *, hot: bool) -> ItemState:
        item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        item_obj.location = self.giver
        item_obj.save()
        instance = ItemInstanceFactory(
            game_object=item_obj, holder_character_sheet=self.giver_sheet
        )
        if hot:
            OwnershipEvent.objects.create(
                item_instance=instance,
                event_type=OwnershipEventType.STOLEN,
                from_character_sheet=self.victim_sheet,
                to_character_sheet=self.giver_sheet,
            )
        return ItemState(instance, context=MagicMock())

    def _set_recipient_mode(self, mode: str) -> None:
        preference = set_social_consent_preference(self.recipient_tenure, allow_social_actions=True)
        set_social_consent_category_rule(preference, receiving_stolen_goods_category(), mode)

    def test_clean_item_ignores_consent(self) -> None:
        self._set_recipient_mode(ConsentMode.ALLOWLIST)
        item = self._held_item(hot=False)
        give(self.giver_state, self.recipient_state, item)
        self.assertEqual(item.instance.holder_character_sheet, self.recipient_sheet)

    def test_hot_item_refused_by_default_deny(self) -> None:
        self._set_recipient_mode(ConsentMode.ALLOWLIST)
        item = self._held_item(hot=True)
        with self.assertRaises(RecipientConsentDenied):
            give(self.giver_state, self.recipient_state, item)
        self.assertEqual(item.instance.holder_character_sheet, self.giver_sheet)

    def test_hot_item_allowed_for_whitelisted_giver(self) -> None:
        giver_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.giver_sheet),
            end_date=None,
        )
        self._set_recipient_mode(ConsentMode.ALLOWLIST)
        add_social_consent_whitelist(
            self.recipient_tenure, giver_tenure, receiving_stolen_goods_category()
        )
        item = self._held_item(hot=True)
        give(self.giver_state, self.recipient_state, item)
        self.assertEqual(item.instance.holder_character_sheet, self.recipient_sheet)

    def test_npc_recipient_unaffected(self) -> None:
        npc = CharacterFactory(db_key="NPCBuyer", location=self.room)
        CharacterSheetFactory(character=npc)
        npc_state = CharacterState(npc, context=MagicMock())
        item = self._held_item(hot=True)
        give(self.giver_state, npc_state, item)
        self.assertIsNotNone(item.instance.holder_character_sheet)
