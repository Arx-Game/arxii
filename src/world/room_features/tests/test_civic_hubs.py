"""Civic-hub reader features (#1450): seeds, progression strategies, hub lookup."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.npc_services.models import Functionary
from world.projects.factories import ProjectFactory
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.models import RoomFeatureInstance, RoomFeatureProgressionDetails
from world.room_features.seeds import (
    TOWN_CRIER_ROLE_NAME,
    ensure_notice_board_kind,
    ensure_town_crier_kind,
)
from world.room_features.services import (
    active_hub_feature,
    handle_notice_board_progression,
    handle_town_crier_progression,
)


class CivicHubFeatureTests(TestCase):
    def setUp(self) -> None:
        self.board_kind = ensure_notice_board_kind()
        self.crier_kind = ensure_town_crier_kind()
        self.room_profile = RoomProfileFactory()

    def _progression(self, kind, target_level: int = 1):
        project = ProjectFactory()
        RoomFeatureProgressionDetails.objects.create(
            project=project,
            target_room_profile=self.room_profile,
            target_feature_kind=kind,
            target_level=target_level,
        )
        return project

    def test_seeds_are_idempotent(self) -> None:
        self.assertEqual(ensure_notice_board_kind().pk, self.board_kind.pk)
        self.assertEqual(ensure_town_crier_kind().pk, self.crier_kind.pk)
        self.assertEqual(self.board_kind.service_strategy, RoomFeatureServiceStrategy.NOTICE_BOARD)
        self.assertEqual(self.crier_kind.service_strategy, RoomFeatureServiceStrategy.TOWN_CRIER)

    def test_board_install_creates_the_instance_only(self) -> None:
        handle_notice_board_progression(self._progression(self.board_kind), 1, None)
        instance = RoomFeatureInstance.objects.filter(room_profile=self.room_profile).get()
        self.assertEqual(instance.feature_kind, self.board_kind)
        self.assertFalse(Functionary.objects.filter(room=self.room_profile).exists())

    def test_crier_install_places_the_crier_functionary(self) -> None:
        handle_town_crier_progression(self._progression(self.crier_kind), 1, None)
        instance = RoomFeatureInstance.objects.filter(room_profile=self.room_profile).get()
        self.assertEqual(instance.feature_kind, self.crier_kind)
        functionary = Functionary.objects.get(room=self.room_profile, is_active=True)
        self.assertEqual(functionary.role.name, TOWN_CRIER_ROLE_NAME)

    def test_crier_reinstall_is_idempotent_on_the_functionary(self) -> None:
        handle_town_crier_progression(self._progression(self.crier_kind), 1, None)
        handle_town_crier_progression(self._progression(self.crier_kind), 1, None)
        self.assertEqual(Functionary.objects.filter(room=self.room_profile).count(), 1)

    def test_active_hub_feature_finds_board_and_crier(self) -> None:
        self.assertIsNone(active_hub_feature(self.room_profile))
        handle_notice_board_progression(self._progression(self.board_kind), 1, None)
        feature = active_hub_feature(self.room_profile)
        self.assertIsNotNone(feature)
        self.assertEqual(feature.feature_kind, self.board_kind)

    def test_active_hub_feature_ignores_non_hub_kinds(self) -> None:
        from world.room_features.seeds import ensure_command_center_kind

        RoomFeatureInstance.objects.create(
            room_profile=self.room_profile,
            feature_kind=ensure_command_center_kind(),
            level=1,
        )
        self.assertIsNone(active_hub_feature(self.room_profile))
