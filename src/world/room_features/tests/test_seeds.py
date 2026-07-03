"""Seed helper tests not covered by their own dedicated test module."""

from django.test import TestCase

from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.seeds import ensure_lab_kind


class EnsureLabKindTests(TestCase):
    def test_creates_lab_kind(self) -> None:
        kind = ensure_lab_kind()
        self.assertEqual(kind.service_strategy, RoomFeatureServiceStrategy.LAB)
        self.assertEqual(kind.max_level, 5)

    def test_idempotent(self) -> None:
        first = ensure_lab_kind()
        second = ensure_lab_kind()
        self.assertEqual(first.pk, second.pk)
