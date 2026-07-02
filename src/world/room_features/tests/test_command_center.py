"""Command Center room feature (#930): seed + progression strategy."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.projects.factories import ProjectFactory
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.models import (
    RoomFeatureInstance,
    RoomFeatureProgressionDetails,
)
from world.room_features.seeds import ensure_command_center_kind
from world.room_features.services import handle_command_center_progression


class CommandCenterTests(TestCase):
    def setUp(self) -> None:
        self.kind = ensure_command_center_kind()
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

    def test_seed_is_idempotent(self) -> None:
        again = ensure_command_center_kind()
        self.assertEqual(self.kind.pk, again.pk)
        self.assertEqual(again.service_strategy, RoomFeatureServiceStrategy.COMMAND_CENTER)

    def test_level_one_installs_the_feature(self) -> None:
        project = self._progression(1)
        handle_command_center_progression(project, 1, None)
        instance = RoomFeatureInstance.objects.filter(room_profile=self.room_profile).get()
        self.assertEqual(instance.feature_kind, self.kind)
        self.assertEqual(instance.level, 1)

    def test_higher_target_levels_the_existing_instance(self) -> None:
        handle_command_center_progression(self._progression(1), 1, None)
        handle_command_center_progression(self._progression(3), 3, None)
        instance = RoomFeatureInstance.objects.filter(room_profile=self.room_profile).get()
        self.assertEqual(instance.level, 3)

    def test_lower_target_never_downgrades(self) -> None:
        handle_command_center_progression(self._progression(3), 3, None)
        handle_command_center_progression(self._progression(2), 2, None)
        instance = RoomFeatureInstance.objects.filter(room_profile=self.room_profile).get()
        self.assertEqual(instance.level, 3)
