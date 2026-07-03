from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.items.crafting.constants import LAB_BASE_DURABILITY_PER_LEVEL
from world.items.crafting.models import LabStationDetails
from world.items.crafting.station import handle_lab_progression
from world.projects.factories import ProjectFactory
from world.room_features.models import RoomFeatureInstance, RoomFeatureProgressionDetails
from world.room_features.seeds import ensure_lab_kind


class HandleLabProgressionTests(TestCase):
    def setUp(self) -> None:
        self.kind = ensure_lab_kind()
        self.room_profile = RoomProfileFactory()

    def _progression(self, target_level: int):
        project = ProjectFactory()
        RoomFeatureProgressionDetails.objects.create(
            project=project,
            target_room_profile=self.room_profile,
            target_feature_kind=self.kind,
            target_level=target_level,
        )
        return project

    def test_install_creates_instance_and_full_durability_station(self) -> None:
        handle_lab_progression(self._progression(1), 1, None)
        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        station = LabStationDetails.objects.get(feature_instance=instance)
        self.assertEqual(instance.level, 1)
        self.assertEqual(station.max_durability, LAB_BASE_DURABILITY_PER_LEVEL)
        self.assertEqual(station.durability, LAB_BASE_DURABILITY_PER_LEVEL)

    def test_upgrade_recomputes_max_and_refills_durability(self) -> None:
        handle_lab_progression(self._progression(1), 1, None)
        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        station = LabStationDetails.objects.get(feature_instance=instance)
        station.durability = 3  # simulate wear before upgrading
        station.save(update_fields=["durability"])

        handle_lab_progression(self._progression(3), 3, None)

        instance.refresh_from_db()
        station.refresh_from_db()
        self.assertEqual(instance.level, 3)
        self.assertEqual(station.max_durability, LAB_BASE_DURABILITY_PER_LEVEL * 3)
        self.assertEqual(station.durability, LAB_BASE_DURABILITY_PER_LEVEL * 3)

    def test_lower_target_never_downgrades(self) -> None:
        handle_lab_progression(self._progression(3), 3, None)
        handle_lab_progression(self._progression(2), 2, None)
        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        self.assertEqual(instance.level, 3)
