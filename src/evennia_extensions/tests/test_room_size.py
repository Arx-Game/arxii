"""Tests for the RoomSizeTier ladder + RoomProfile size/grid fields (#670)."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from evennia_extensions.models import RoomSizeTier
from evennia_extensions.seeds import ensure_room_size_tiers


class RoomSizeTierTests(TestCase):
    def test_ordering_by_units(self) -> None:
        RoomSizeTier.objects.create(name="Grand", units=100)
        RoomSizeTier.objects.create(name="Micro", units=2)
        names = list(RoomSizeTier.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Micro", "Grand"])

    def test_str(self) -> None:
        tier = RoomSizeTier.objects.create(name="Snug", units=10)
        self.assertEqual(str(tier), "Snug (10 units)")


class RoomProfileSizeTests(TestCase):
    def test_size_nullable_default_none(self) -> None:
        profile = RoomProfileFactory()
        self.assertIsNone(profile.size)

    def test_grid_fields_default_unplaced(self) -> None:
        profile = RoomProfileFactory()
        self.assertIsNone(profile.grid_x)
        self.assertIsNone(profile.grid_y)
        self.assertEqual(profile.floor, 0)


class RoomSizeSeedTests(TestCase):
    def test_seed_ladder_loads(self) -> None:
        ensure_room_size_tiers()
        tiers = list(RoomSizeTier.objects.values_list("name", "units"))
        self.assertEqual(len(tiers), 9)
        self.assertIn(("Modest", 25), tiers)
        self.assertEqual(tiers[0], ("Micro", 2))
        self.assertEqual(tiers[-1], ("Expanse", 2500))
        # Idempotent re-run.
        ensure_room_size_tiers()
        self.assertEqual(RoomSizeTier.objects.count(), 9)
