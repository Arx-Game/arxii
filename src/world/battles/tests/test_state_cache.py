"""Tests for BattleStateCache (#1846)."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.battles.constants import BattleParticipantStatus, BattleUnitStatus
from world.battles.factories import (
    BattleFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
    BattleVehicleFactory,
)
from world.battles.models import BattleParticipant
from world.character_sheets.factories import CharacterSheetFactory


class BattleStateCacheRegistrationTests(TestCase):
    """Verify register-on-create fires from model save(), not just services.py."""

    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)

    def test_unit_created_via_factory_is_registered(self) -> None:
        """A BattleUnit created via the bare factory (not add_unit()) still
        registers -- registration happens in BattleUnit.save(), not services.py.
        """
        unit = BattleUnitFactory(battle=self.battle, side=self.side)
        cached = self.battle.state_cache.units_on_side(self.side.pk)
        self.assertIn(unit, cached)

    def test_participant_created_via_factory_is_registered(self) -> None:
        sheet = CharacterSheetFactory()
        participant = BattleParticipant.objects.create(
            battle=self.battle,
            character_sheet=sheet,
            side=self.side,
            status=BattleParticipantStatus.ACTIVE,
        )
        cached = self.battle.state_cache.participants_on_side(self.side.pk)
        self.assertIn(participant, cached)

    def test_units_on_place_is_query_free_after_registration(self) -> None:
        place = BattlePlaceFactory(battle=self.battle)
        unit = BattleUnitFactory(battle=self.battle, side=self.side, place=place)
        with CaptureQueriesContext(connection) as ctx:
            result = self.battle.state_cache.units_on_place(place.pk)
        self.assertEqual(len(ctx), 0)
        self.assertEqual(result, [unit])

    def test_status_filter_reads_current_in_memory_status(self) -> None:
        """Status filtering is a read-time scan, not a bucket move -- a unit's
        status change (via .save()) is immediately visible with no re-registration."""
        unit = BattleUnitFactory(battle=self.battle, side=self.side, status=BattleUnitStatus.ACTIVE)
        active = self.battle.state_cache.units_on_side(
            self.side.pk, statuses=(BattleUnitStatus.ACTIVE,)
        )
        self.assertIn(unit, active)

        unit.status = BattleUnitStatus.DESTROYED
        unit.save(update_fields=["status"])

        active_after = self.battle.state_cache.units_on_side(
            self.side.pk, statuses=(BattleUnitStatus.ACTIVE,)
        )
        destroyed_after = self.battle.state_cache.units_on_side(
            self.side.pk, statuses=(BattleUnitStatus.DESTROYED,)
        )
        self.assertNotIn(unit, active_after)
        self.assertIn(unit, destroyed_after)

    def test_vehicle_lookup_by_unit_and_place(self) -> None:
        vehicle = BattleVehicleFactory(unit__battle=self.battle, unit__side=self.side)
        self.assertEqual(self.battle.state_cache.vehicle_for_unit(vehicle.unit_id), vehicle)
        self.assertEqual(self.battle.state_cache.vehicle_at_place(vehicle.place_id), vehicle)


class BattleStateCacheColdStartTests(TestCase):
    """Verify the cold-start fallback loads a battle whose cache was evicted."""

    def test_fresh_cache_instance_loads_existing_rows(self) -> None:
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side)

        # Simulate a process restart: drop the cache attribute entirely,
        # forcing the next .state_cache access to build a fresh instance
        # that must cold-start-load from the DB.
        del battle._state_cache

        with CaptureQueriesContext(connection) as ctx:
            result = battle.state_cache.units_on_side(side.pk)
        self.assertGreater(len(ctx), 0)  # cold start DOES query, once
        self.assertEqual(result, [unit])


class BattleStateCacheMoveTests(TestCase):
    """Verify move_unit_place()/move_participant_place() re-bucket correctly."""

    def test_move_unit_place_updates_buckets(self) -> None:
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        old_place = BattlePlaceFactory(battle=battle, name="Old Front")
        unit = BattleUnitFactory(battle=battle, side=side, place=old_place)

        unit.place = None
        unit.save(update_fields=["place"])
        battle.state_cache.move_unit_place(unit, old_place_id=old_place.pk)

        self.assertNotIn(unit, battle.state_cache.units_on_place(old_place.pk))
