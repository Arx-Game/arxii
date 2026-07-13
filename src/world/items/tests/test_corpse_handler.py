"""Corpse trusted-handler exemption tests (#2289).

A dead owner's gear routes through steal — unless the dead player's tenure
friended the taker's (the friends-list dovetail). Living owners are never
exempted.
"""

from __future__ import annotations

from django.test import TestCase

from flows.service_functions.inventory import take_requires_steal
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.friend_services import add_friend
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory


class CorpseHandlerExemptionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.dead_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=cls.dead_sheet, life_state=CharacterLifeState.DEAD)
        cls.dead_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=cls.dead_sheet)
        )
        cls.taker_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=cls.taker_sheet)
        cls.taker_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=cls.taker_sheet)
        )

    def _corpse_item(self):
        return ItemInstanceFactory(holder_character_sheet=self.dead_sheet)

    def test_stranger_still_requires_steal(self) -> None:
        item = self._corpse_item()
        self.assertTrue(take_requires_steal(self.taker_sheet, item))

    def test_friend_of_the_dead_takes_freely(self) -> None:
        add_friend(friender_tenure=self.dead_tenure, friend_tenure=self.taker_tenure)
        item = self._corpse_item()
        self.assertFalse(take_requires_steal(self.taker_sheet, item))

    def test_living_owner_friend_gets_no_exemption(self) -> None:
        living_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=living_sheet)
        living_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=living_sheet)
        )
        add_friend(friender_tenure=living_tenure, friend_tenure=self.taker_tenure)
        item = ItemInstanceFactory(holder_character_sheet=living_sheet)
        self.assertTrue(take_requires_steal(self.taker_sheet, item))

    def test_friendship_direction_matters(self) -> None:
        # The TAKER friended the dead — not the reverse. No exemption: trust
        # must come from the dead player's side.
        add_friend(friender_tenure=self.taker_tenure, friend_tenure=self.dead_tenure)
        item = self._corpse_item()
        self.assertTrue(take_requires_steal(self.taker_sheet, item))
