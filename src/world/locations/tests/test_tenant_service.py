from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationTenancy
from world.locations.services import current_tenants
from world.scenes.factories import PersonaFactory


class CurrentTenantsTests(TestCase):
    def setUp(self) -> None:
        self.building = AreaFactory(level=AreaLevel.BUILDING)
        self.profile = RoomProfileFactory(area=self.building)
        self.room = self.profile.objectdb

    def test_no_tenancies_returns_empty(self) -> None:
        self.assertEqual(list(current_tenants(self.room)), [])

    def test_room_level_tenancy_returned(self) -> None:
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        self.assertEqual(list(current_tenants(self.room)), [row])

    def test_area_level_tenancy_returned_for_room_within(self) -> None:
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        self.assertEqual(list(current_tenants(self.room)), [row])

    def test_multiple_concurrent_tenancies_all_returned(self) -> None:
        building_tenant = LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        room_tenant_1 = LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        room_tenant_2 = LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        result = set(current_tenants(self.room))
        self.assertEqual(result, {building_tenant, room_tenant_1, room_tenant_2})

    def test_expired_tenancy_excluded(self) -> None:
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
            ends_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(list(current_tenants(self.room)), [])

    def test_future_ends_at_included(self) -> None:
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
            ends_at=timezone.now() + timedelta(days=30),
        )
        self.assertEqual(list(current_tenants(self.room)), [row])

    def test_query_budget_two_queries_per_call(self) -> None:
        """Current tenants fires exactly 2 queries: AreaClosure walk +
        LocationTenancy fetch with tenant/area joined via
        select_related. ``room.room_profile`` is served from the
        SharedMemoryModel identity map (no extra query) because the
        profile was loaded upstream in setUp; walking
        ``t.tenant_persona`` is satisfied by select_related.
        """
        LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        from evennia.objects.models import ObjectDB

        room = ObjectDB.objects.get(pk=self.room.pk)
        with self.assertNumQueries(2):
            rows = list(current_tenants(room))
            for t in rows:
                _ = t.tenant_persona  # walk confirms prefetch

    def test_unrelated_area_tenancy_not_returned(self) -> None:
        other_building = AreaFactory(level=AreaLevel.BUILDING)
        LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=other_building,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        self.assertEqual(list(current_tenants(self.room)), [])


class CurrentTenantsEdgeCaseTests(TestCase):
    def test_room_with_no_profile_returns_empty(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()
        self.assertEqual(list(current_tenants(room)), [])

    def test_room_with_profile_but_no_area_returns_room_level_only(self) -> None:
        profile = RoomProfileFactory()  # area defaults to None
        self.assertIsNone(profile.area)
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        self.assertEqual(list(current_tenants(profile.objectdb)), [row])
