from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.items.crafting.models import LabStationDetails
from world.items.crafting.station import repair_station_durability
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory


class RepairStationDurabilityTests(TestCase):
    def setUp(self) -> None:
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        instance = RoomFeatureInstanceFactory(
            room_profile=RoomProfileFactory(), feature_kind=kind, level=2
        )
        self.station = LabStationDetails.objects.create(
            feature_instance=instance, durability=10, max_durability=40
        )
        self.sheet = CharacterSheetFactory()
        self.purse = get_or_create_purse(self.sheet)
        self.purse.balance = 10_000
        self.purse.save(update_fields=["balance"])

    def test_repair_clamps_to_deficit_and_charges_correct_cost(self) -> None:
        repair_station_durability(station=self.station, restore_points=100, payer_purse=self.purse)
        self.station.refresh_from_db()
        self.purse.refresh_from_db()
        # clamped to 40-10=30 points restored, at level=2 → 15*2=30 copper/point
        self.assertEqual(self.station.durability, 40)
        self.assertEqual(self.purse.balance, 10_000 - 30 * 30)

    def test_insufficient_funds_raises_and_does_not_mutate_durability(self) -> None:
        self.purse.balance = 1
        self.purse.save(update_fields=["balance"])
        with self.assertRaises(ValidationError):
            repair_station_durability(
                station=self.station, restore_points=5, payer_purse=self.purse
            )
        self.station.refresh_from_db()
        self.assertEqual(self.station.durability, 10)
