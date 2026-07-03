"""E2E: install a Lab, craft against it until it breaks, get blocked, repair, craft again (#1234).

Exercises the real station gate/wear/repair pipeline end to end through the public
``craft_attach_facet``/``repair_station_durability`` entry points — not the
project-installation machinery. Station installation uses ``install_full_lab_station``
(Task 10's test-fixture helper), which creates the ``RoomFeatureInstance`` +
full-durability ``LabStationDetails`` directly rather than driving a fake
``Project`` through ``handle_lab_progression``; that install path is already
covered by its own tests (``test_lab_station_progression.py``).
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.items.crafting.station import repair_station_durability
from world.items.exceptions import CraftingStationBroken, CraftingStationRequired
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.services.crafting import craft_attach_facet
from world.magic.factories import FacetFactory


class CraftingStationEconomyE2ETests(TestCase):
    """A player installs a Lab, wears it out crafting, gets blocked, then repairs it."""

    def setUp(self) -> None:
        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        self.room_profile = RoomProfileFactory()
        self.character.location = self.room_profile.objectdb
        self.character.save()

    def _item(self):
        template = ItemTemplateFactory(facet_capacity=10)
        return ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)

    def _craft(self):
        return craft_attach_facet(
            crafter_account=self.account,
            crafter_character=self.character,
            item_instance=self._item(),
            facet=FacetFactory(),
        )

    def test_no_station_blocks_crafting(self) -> None:
        with self.assertRaises(CraftingStationRequired):
            self._craft()

    def test_full_journey_install_craft_break_block_repair_craft(self) -> None:
        station = install_full_lab_station(self.room_profile, level=1)
        max_durability = station.max_durability

        for _ in range(max_durability):
            self._craft()  # succeeds or fails the check; either way, station wears
        station.refresh_from_db()
        self.assertTrue(station.is_broken)
        self.assertEqual(station.durability, 0)

        with self.assertRaises(CraftingStationBroken):
            self._craft()

        purse = get_or_create_purse(self.sheet)
        purse.balance = 100_000
        purse.save(update_fields=["balance"])
        repair_station_durability(station=station, restore_points=max_durability, payer_purse=purse)
        station.refresh_from_db()
        self.assertFalse(station.is_broken)
        self.assertEqual(station.durability, max_durability)

        result = self._craft()  # no longer raises
        self.assertIsNotNone(result)
        station.refresh_from_db()
        self.assertEqual(station.durability, max_durability - 1)
