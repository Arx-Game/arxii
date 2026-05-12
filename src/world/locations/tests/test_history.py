from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.factories import (
    LocationOwnershipFactory,
    LocationTenancyFactory,
)
from world.locations.models import LocationOwnership, LocationTenancy
from world.locations.services import ownership_history_for, tenancy_history_for
from world.scenes.factories import PersonaFactory


class OwnershipHistoryForTests(TestCase):
    def test_returns_all_rows_ordered_by_acquired_at(self) -> None:
        area = AreaFactory()
        now = timezone.now()
        # The partial-unique constraint forbids two active rows per area,
        # so end older rows before adding newer ones. Create out of insert
        # order to verify the service sorts by acquired_at.
        second = LocationOwnershipFactory(
            area=area,
            holder_persona=PersonaFactory(),
            acquired_at=now - timedelta(days=5),
            ended_at=now - timedelta(days=1, hours=1),
        )
        first = LocationOwnershipFactory(
            area=area,
            holder_persona=PersonaFactory(),
            acquired_at=now - timedelta(days=10),
            ended_at=now - timedelta(days=5, hours=1),
        )
        third = LocationOwnershipFactory(
            area=area,
            holder_persona=PersonaFactory(),
            acquired_at=now - timedelta(days=1),
        )
        result = list(ownership_history_for(area=area))
        self.assertEqual(result, [first, second, third])

    def test_includes_ended_rows(self) -> None:
        area = AreaFactory()
        # End the first one before creating the next, so the partial-unique
        # constraint (one active owner per area) stays satisfied.
        ended = LocationOwnershipFactory(area=area, holder_persona=PersonaFactory())
        ended.ended_at = timezone.now()
        ended.save()
        active = LocationOwnershipFactory(area=area, holder_persona=PersonaFactory())
        result = set(ownership_history_for(area=area))
        self.assertEqual(result, {active, ended})

    def test_excludes_unrelated_locations(self) -> None:
        target_area = AreaFactory()
        other_area = AreaFactory()
        mine = LocationOwnershipFactory(area=target_area, holder_persona=PersonaFactory())
        LocationOwnershipFactory(area=other_area, holder_persona=PersonaFactory())
        result = list(ownership_history_for(area=target_area))
        self.assertEqual(result, [mine])

    def test_empty_when_no_rows(self) -> None:
        area = AreaFactory()
        self.assertEqual(list(ownership_history_for(area=area)), [])

    def test_works_for_room_profile(self) -> None:
        profile = RoomProfileFactory()
        row = LocationOwnershipFactory(
            on_room=True, room_profile=profile, holder_persona=PersonaFactory()
        )
        result = list(ownership_history_for(room_profile=profile))
        self.assertEqual(result, [row])

    def test_validation_missing_both(self) -> None:
        with self.assertRaises(ValueError):
            ownership_history_for()

    def test_validation_both_set(self) -> None:
        with self.assertRaises(ValueError):
            ownership_history_for(area=AreaFactory(), room_profile=RoomProfileFactory())

    def test_returns_location_ownership_type(self) -> None:
        area = AreaFactory()
        LocationOwnershipFactory(area=area, holder_persona=PersonaFactory())
        result = ownership_history_for(area=area)
        # QuerySet of the correct model
        self.assertEqual(result.model, LocationOwnership)


class TenancyHistoryForTests(TestCase):
    def test_returns_all_rows_ordered_by_started_at(self) -> None:
        building = AreaFactory()
        now = timezone.now()
        second = LocationTenancyFactory(
            on_area=True,
            area=building,
            tenant_persona=PersonaFactory(),
            started_at=now - timedelta(days=5),
        )
        first = LocationTenancyFactory(
            on_area=True,
            area=building,
            tenant_persona=PersonaFactory(),
            started_at=now - timedelta(days=10),
        )
        third = LocationTenancyFactory(
            on_area=True,
            area=building,
            tenant_persona=PersonaFactory(),
            started_at=now - timedelta(days=1),
        )
        result = list(tenancy_history_for(area=building))
        self.assertEqual(result, [first, second, third])

    def test_includes_ended_rows(self) -> None:
        building = AreaFactory()
        active = LocationTenancyFactory(
            on_area=True, area=building, tenant_persona=PersonaFactory()
        )
        ended = LocationTenancyFactory(
            on_area=True,
            area=building,
            tenant_persona=PersonaFactory(),
            ends_at=timezone.now() - timedelta(days=1),
        )
        result = set(tenancy_history_for(area=building))
        self.assertEqual(result, {active, ended})

    def test_excludes_unrelated_locations(self) -> None:
        target_building = AreaFactory()
        other_building = AreaFactory()
        mine = LocationTenancyFactory(
            on_area=True, area=target_building, tenant_persona=PersonaFactory()
        )
        LocationTenancyFactory(on_area=True, area=other_building, tenant_persona=PersonaFactory())
        result = list(tenancy_history_for(area=target_building))
        self.assertEqual(result, [mine])

    def test_works_for_room_profile(self) -> None:
        profile = RoomProfileFactory()
        row = LocationTenancyFactory(room_profile=profile, tenant_persona=PersonaFactory())
        result = list(tenancy_history_for(room_profile=profile))
        self.assertEqual(result, [row])

    def test_validation_missing_both(self) -> None:
        with self.assertRaises(ValueError):
            tenancy_history_for()

    def test_validation_both_set(self) -> None:
        with self.assertRaises(ValueError):
            tenancy_history_for(area=AreaFactory(), room_profile=RoomProfileFactory())

    def test_returns_location_tenancy_type(self) -> None:
        building = AreaFactory()
        LocationTenancyFactory(on_area=True, area=building, tenant_persona=PersonaFactory())
        result = tenancy_history_for(area=building)
        self.assertEqual(result.model, LocationTenancy)


class HistoryDeterministicOrderingTests(TestCase):
    def test_ownership_tied_timestamps_break_by_pk(self) -> None:
        area = AreaFactory()
        same_ts = timezone.now() - timedelta(days=1)
        first = LocationOwnershipFactory(
            area=area, holder_persona=PersonaFactory(), acquired_at=same_ts
        )
        first.ended_at = timezone.now()
        first.save()
        second = LocationOwnershipFactory(
            area=area, holder_persona=PersonaFactory(), acquired_at=same_ts
        )
        # First created has the smaller pk; tiebreaker should put it first.
        result = list(ownership_history_for(area=area))
        self.assertEqual(result, [first, second])

    def test_tenancy_tied_timestamps_break_by_pk(self) -> None:
        building = AreaFactory()
        same_ts = timezone.now() - timedelta(days=1)
        first = LocationTenancyFactory(
            on_area=True,
            area=building,
            tenant_persona=PersonaFactory(),
            started_at=same_ts,
        )
        second = LocationTenancyFactory(
            on_area=True,
            area=building,
            tenant_persona=PersonaFactory(),
            started_at=same_ts,
        )
        result = list(tenancy_history_for(area=building))
        self.assertEqual(result, [first, second])
