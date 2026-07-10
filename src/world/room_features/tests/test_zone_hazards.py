"""Tests for zone hazard lifecycle (#2019)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.room_features.factories import TrapFactory
from world.room_features.trap_services import (
    teardown_conjured_hazards,
    tick_zone_hazards,
)


class ZoneHazardLifecycleTest(TestCase):
    """Zone hazards (Traps with duration_rounds) tick down and disarm (#2019)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.trap = TrapFactory(duration_rounds=3, created_by_sheet=self.sheet)

    def test_zone_hazard_has_duration(self) -> None:
        self.assertEqual(self.trap.duration_rounds, 3)
        self.assertEqual(self.trap.created_by_sheet, self.sheet)

    def test_tick_decrements_duration(self) -> None:
        """Each tick decrements duration_rounds by 1."""
        room = self.trap.room_profile.objectdb
        tick_zone_hazards(room)
        self.trap.refresh_from_db()
        self.assertEqual(self.trap.duration_rounds, 2)
        self.assertTrue(self.trap.is_armed)

    def test_tick_disarms_at_zero(self) -> None:
        """When duration reaches 0, the hazard is disarmed."""
        room = self.trap.room_profile.objectdb
        for _ in range(3):
            tick_zone_hazards(room)
        self.trap.refresh_from_db()
        self.assertFalse(self.trap.is_armed)

    def test_tick_skips_staff_traps(self) -> None:
        """Staff-authored traps (null duration_rounds) are never decremented."""
        staff_trap = TrapFactory(duration_rounds=None, created_by_sheet=None)
        room = staff_trap.room_profile.objectdb
        tick_zone_hazards(room)
        staff_trap.refresh_from_db()
        self.assertTrue(staff_trap.is_armed)
        self.assertIsNone(staff_trap.duration_rounds)

    def test_teardown_disarms_conjured(self) -> None:
        """teardown_conjured_hazards disarms all conjured hazards."""
        from evennia.utils.idmapper.models import flush_cache

        room = self.trap.room_profile.objectdb
        teardown_conjured_hazards(room)
        # SharedMemoryModel caches in memory; flush to read the DB-updated state.
        flush_cache()
        from world.room_features.models import Trap

        refreshed = Trap.objects.get(pk=self.trap.pk)
        self.assertFalse(refreshed.is_armed)

    def test_teardown_preserves_staff_traps(self) -> None:
        """Staff-authored traps are not disarmed by teardown."""
        staff_trap = TrapFactory(duration_rounds=None, created_by_sheet=None)
        room = staff_trap.room_profile.objectdb
        teardown_conjured_hazards(room)
        staff_trap.refresh_from_db()
        self.assertTrue(staff_trap.is_armed)
