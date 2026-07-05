"""Seed helper tests not covered by their own dedicated test module."""

from django.test import TestCase

from world.room_features.constants import (
    RoomFeatureInstallMechanism,
    RoomFeatureServiceStrategy,
)
from world.room_features.seeds import (
    ensure_captains_quarters_kind,
    ensure_lab_kind,
    ensure_library_kind,
    ensure_siege_deck_kind,
    ensure_training_room_kind,
)


class EnsureLabKindTests(TestCase):
    def test_creates_lab_kind(self) -> None:
        kind = ensure_lab_kind()
        self.assertEqual(kind.service_strategy, RoomFeatureServiceStrategy.LAB)
        self.assertEqual(kind.max_level, 5)

    def test_idempotent(self) -> None:
        first = ensure_lab_kind()
        second = ensure_lab_kind()
        self.assertEqual(first.pk, second.pk)


class EnsureLibraryKindTests(TestCase):
    def test_creates_library_kind(self) -> None:
        kind = ensure_library_kind()
        self.assertEqual(kind.service_strategy, RoomFeatureServiceStrategy.LIBRARY)
        self.assertEqual(kind.max_level, 10)
        self.assertEqual(kind.install_mechanism, RoomFeatureInstallMechanism.PROJECT)

    def test_idempotent(self) -> None:
        first = ensure_library_kind()
        second = ensure_library_kind()
        self.assertEqual(first.pk, second.pk)


class EnsureTrainingRoomKindTests(TestCase):
    def test_creates_training_room_kind(self) -> None:
        kind = ensure_training_room_kind()
        self.assertEqual(kind.service_strategy, RoomFeatureServiceStrategy.TRAINING_ROOM)
        self.assertEqual(kind.max_level, 3)
        self.assertEqual(kind.install_mechanism, RoomFeatureInstallMechanism.PROJECT)

    def test_idempotent(self) -> None:
        first = ensure_training_room_kind()
        second = ensure_training_room_kind()
        self.assertEqual(first.pk, second.pk)


class EnsureSiegeDeckKindTests(TestCase):
    def test_creates_siege_deck_kind(self) -> None:
        from world.ships.seeds import ensure_ship_kind

        kind = ensure_siege_deck_kind()
        self.assertEqual(kind.service_strategy, RoomFeatureServiceStrategy.SIEGE_DECK)
        self.assertEqual(kind.max_level, 5)
        self.assertEqual(kind.install_mechanism, RoomFeatureInstallMechanism.PROJECT)
        # Maritime-gated: the Vessel BuildingKind is in allowed_building_kinds.
        ship_kind = ensure_ship_kind()
        self.assertIn(ship_kind, kind.allowed_building_kinds.all())

    def test_idempotent(self) -> None:
        first = ensure_siege_deck_kind()
        second = ensure_siege_deck_kind()
        self.assertEqual(first.pk, second.pk)


class EnsureCaptainsQuartersKindTests(TestCase):
    def test_creates_captains_quarters_kind(self) -> None:
        from world.ships.seeds import ensure_ship_kind

        kind = ensure_captains_quarters_kind()
        self.assertEqual(kind.service_strategy, RoomFeatureServiceStrategy.CAPTAINS_QUARTERS)
        self.assertEqual(kind.max_level, 1)
        self.assertEqual(kind.install_mechanism, RoomFeatureInstallMechanism.PROJECT)
        ship_kind = ensure_ship_kind()
        self.assertIn(ship_kind, kind.allowed_building_kinds.all())

    def test_idempotent(self) -> None:
        first = ensure_captains_quarters_kind()
        second = ensure_captains_quarters_kind()
        self.assertEqual(first.pk, second.pk)
