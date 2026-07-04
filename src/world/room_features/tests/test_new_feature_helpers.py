"""Tests for the four #675 feature-kind helpers + progression handlers.

The active_<kind>_in helpers find the right instance by service_strategy.
The handlers are thin wrappers over _install_or_level_feature (like Command
Center / Notice Board); their correctness is proven by the existing
ROOM_FEATURE_PROGRESSION Project resolution flow, so these tests focus on
the read-time lookup helpers (the consumer-side hooks depend on them).
"""

from django.test import TestCase

from world.room_features.factories import RoomFeatureInstanceFactory
from world.room_features.seeds import (
    ensure_captains_quarters_kind,
    ensure_library_kind,
    ensure_siege_deck_kind,
    ensure_training_room_kind,
)
from world.room_features.services import (
    active_captains_quarters_in,
    active_library_in,
    active_siege_deck_in,
    active_training_room_in,
)


class ActiveLibraryInTests(TestCase):
    def test_finds_library_instance(self) -> None:
        kind = ensure_library_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        found = active_library_in(instance.room_profile)
        self.assertEqual(found, instance)

    def test_returns_none_when_no_library(self) -> None:
        instance = RoomFeatureInstanceFactory()
        self.assertIsNone(active_library_in(instance.room_profile))

    def test_excludes_dissolved(self) -> None:
        kind = ensure_library_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        instance.dissolved_at = instance.installed_at
        instance.save(update_fields=["dissolved_at"])
        self.assertIsNone(active_library_in(instance.room_profile))


class ActiveTrainingRoomInTests(TestCase):
    def test_finds_training_room_instance(self) -> None:
        kind = ensure_training_room_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        found = active_training_room_in(instance.room_profile)
        self.assertEqual(found, instance)

    def test_returns_none_when_absent(self) -> None:
        instance = RoomFeatureInstanceFactory()
        self.assertIsNone(active_training_room_in(instance.room_profile))


class ActiveSiegeDeckInTests(TestCase):
    def test_finds_siege_deck_instance(self) -> None:
        kind = ensure_siege_deck_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        found = active_siege_deck_in(instance.room_profile)
        self.assertEqual(found, instance)

    def test_returns_none_when_absent(self) -> None:
        instance = RoomFeatureInstanceFactory()
        self.assertIsNone(active_siege_deck_in(instance.room_profile))


class ActiveCaptainsQuartersInTests(TestCase):
    def test_finds_captains_quarters_instance(self) -> None:
        kind = ensure_captains_quarters_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        found = active_captains_quarters_in(instance.room_profile)
        self.assertEqual(found, instance)

    def test_returns_none_when_absent(self) -> None:
        instance = RoomFeatureInstanceFactory()
        self.assertIsNone(active_captains_quarters_in(instance.room_profile))
