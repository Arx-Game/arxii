from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import (
    STAT_DEFAULTS,
    KeyType,
    LocationParentType,
    StatKey,
)
from world.locations.factories import (
    LocationOwnershipFactory,
    LocationTenancyFactory,
    LocationValueModifierFactory,
    LocationValueOverrideFactory,
)
from world.locations.models import LocationValueModifier, LocationValueOverride
from world.locations.services import (
    _bulk_room_profiles_and_ancestors,
    current_tenants,
    effective_owner,
    effective_owners_for_rooms,
    effective_value,
    effective_values_for_rooms,
    tenancies_for_rooms,
)
from world.magic.factories import ResonanceFactory
from world.scenes.factories import PersonaFactory


class BulkRoomProfilesAndAncestorsTests(TestCase):
    def test_empty_input(self) -> None:
        room_to_profile, profile_to_ancestors, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
            []
        )
        self.assertEqual(room_to_profile, {})
        self.assertEqual(profile_to_ancestors, {})
        self.assertEqual(all_ancestor_ids, set())

    def test_single_room_with_profile_and_area(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        room = profile.objectdb
        room_to_profile, profile_to_ancestors, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
            [room]
        )
        self.assertEqual(room_to_profile, {room.pk: profile})
        self.assertIn(profile.pk, profile_to_ancestors)
        self.assertIn(ward.pk, profile_to_ancestors[profile.pk])
        self.assertIn(ward.pk, all_ancestor_ids)

    def test_room_with_no_profile_skipped(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()
        room_to_profile, profile_to_ancestors, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
            [room]
        )
        self.assertEqual(room_to_profile, {})
        self.assertEqual(profile_to_ancestors, {})
        self.assertEqual(all_ancestor_ids, set())

    def test_profile_with_no_area(self) -> None:
        profile = RoomProfileFactory()  # area=None
        room = profile.objectdb
        room_to_profile, profile_to_ancestors, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
            [room]
        )
        self.assertEqual(room_to_profile, {room.pk: profile})
        # Profile is mapped but has no ancestors (area=None)
        self.assertNotIn(profile.pk, profile_to_ancestors)
        self.assertEqual(all_ancestor_ids, set())

    def test_multiple_rooms_shared_area_union(self) -> None:
        city = AreaFactory(level=AreaLevel.CITY)
        ward = AreaFactory(level=AreaLevel.WARD, parent=city)
        profile_a = RoomProfileFactory(area=ward)
        profile_b = RoomProfileFactory(area=ward)
        room_a, room_b = profile_a.objectdb, profile_b.objectdb
        room_to_profile, profile_to_ancestors, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
            [room_a, room_b]
        )
        self.assertEqual(set(room_to_profile.keys()), {room_a.pk, room_b.pk})
        # Both profiles share the same ancestor chain
        self.assertEqual(
            set(profile_to_ancestors[profile_a.pk]),
            set(profile_to_ancestors[profile_b.pk]),
        )
        # Union covers ward + city (closure includes self at depth 0)
        self.assertIn(ward.pk, all_ancestor_ids)
        self.assertIn(city.pk, all_ancestor_ids)

    def test_one_closure_query_regardless_of_room_count(self) -> None:
        # Pre-load profiles via factory so the access doesn't fire queries.
        ward = AreaFactory(level=AreaLevel.WARD)
        profiles = [RoomProfileFactory(area=ward) for _ in range(5)]
        rooms = [p.objectdb for p in profiles]
        # Warm SharedMemoryModel cache for profile access — the factory
        # already created them. The access through room.room_profile may
        # still hit the DB the first time depending on Evennia caching.
        # The KEY assertion is that AreaClosure is queried ONCE.
        with CaptureQueriesContext(connection) as ctx:
            _bulk_room_profiles_and_ancestors(rooms)
        closure_queries = [
            q for q in ctx.captured_queries if "areas_areaclosure" in q["sql"].lower()
        ]
        self.assertEqual(
            len(closure_queries),
            1,
            f"Expected 1 AreaClosure query, got {len(closure_queries)}",
        )


class EffectiveStatsForRoomsTests(TestCase):
    def test_empty_rooms_returns_empty_dict(self) -> None:
        result = effective_values_for_rooms([], stat_keys=[StatKey.CRIME])
        self.assertEqual(result, {})

    def test_empty_stat_keys_returns_empty_per_room(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        result = effective_values_for_rooms([room], stat_keys=[])
        self.assertEqual(result, {room.pk: {}})

    def test_single_room_matches_singular_helper(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        room = profile.objectdb
        LocationValueOverrideFactory(area=ward, stat_key=StatKey.CRIME, value=42)

        bulk_result = effective_values_for_rooms([room], stat_keys=[StatKey.CRIME])
        singular_result = effective_value(room, stat_key=StatKey.CRIME)

        self.assertEqual(bulk_result[room.pk][StatKey.CRIME], singular_result)

    def test_multiple_rooms_distinct_results(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile_a = RoomProfileFactory(area=ward)
        profile_b = RoomProfileFactory(area=ward)
        room_a, room_b = profile_a.objectdb, profile_b.objectdb

        # Room A has a room-level override; Room B uses the ward default
        LocationValueOverrideFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=profile_a,
            stat_key=StatKey.CRIME,
            value=80,
        )

        result = effective_values_for_rooms([room_a, room_b], stat_keys=[StatKey.CRIME])
        self.assertEqual(result[room_a.pk][StatKey.CRIME], 80)
        # Room B falls through to default (no override, no modifier)
        self.assertEqual(
            result[room_b.pk][StatKey.CRIME],
            effective_value(room_b, stat_key=StatKey.CRIME),
        )

    def test_room_without_profile_falls_through_to_defaults(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()

        result = effective_values_for_rooms([room], stat_keys=[StatKey.CRIME, StatKey.LIGHTING])
        self.assertEqual(result[room.pk][StatKey.CRIME], STAT_DEFAULTS[StatKey.CRIME])
        self.assertEqual(result[room.pk][StatKey.LIGHTING], STAT_DEFAULTS[StatKey.LIGHTING])

    def test_query_budget_four_queries(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profiles = [RoomProfileFactory(area=ward) for _ in range(3)]
        rooms = [p.objectdb for p in profiles]
        LocationValueOverrideFactory(area=ward, stat_key=StatKey.CRIME, value=20)
        LocationValueModifierFactory(area=ward, stat_key=StatKey.NOISE, value=10)

        with self.assertNumQueries(4):
            effective_values_for_rooms(rooms, stat_keys=[StatKey.CRIME, StatKey.NOISE])


class EffectiveOwnersForRoomsTests(TestCase):
    def test_empty_rooms_returns_empty_dict(self) -> None:
        self.assertEqual(effective_owners_for_rooms([]), {})

    def test_single_room_matches_singular_helper(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        room = profile.objectdb
        row = LocationOwnershipFactory(area=ward, holder_persona=PersonaFactory())
        result = effective_owners_for_rooms([room])
        self.assertEqual(result[room.pk], row)
        self.assertEqual(result[room.pk], effective_owner(room))

    def test_multiple_rooms_room_override_wins_over_area(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile_a = RoomProfileFactory(area=ward)
        profile_b = RoomProfileFactory(area=ward)
        room_a, room_b = profile_a.objectdb, profile_b.objectdb

        ward_owner = LocationOwnershipFactory(area=ward, holder_persona=PersonaFactory())
        room_owner = LocationOwnershipFactory(
            on_room=True,
            room_profile=profile_a,
            holder_persona=PersonaFactory(),
        )

        result = effective_owners_for_rooms([room_a, room_b])
        self.assertEqual(result[room_a.pk], room_owner)
        self.assertEqual(result[room_b.pk], ward_owner)

    def test_more_specific_area_wins(self) -> None:
        city = AreaFactory(level=AreaLevel.CITY)
        ward = AreaFactory(level=AreaLevel.WARD, parent=city)
        profile = RoomProfileFactory(area=ward)
        room = profile.objectdb

        LocationOwnershipFactory(area=city, holder_persona=PersonaFactory())
        ward_row = LocationOwnershipFactory(area=ward, holder_persona=PersonaFactory())

        result = effective_owners_for_rooms([room])
        self.assertEqual(result[room.pk], ward_row)

    def test_no_ownership_returns_none(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        room = profile.objectdb
        result = effective_owners_for_rooms([room])
        self.assertIsNone(result[room.pk])

    def test_room_without_profile_returns_none(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()
        result = effective_owners_for_rooms([room])
        self.assertIsNone(result[room.pk])

    def test_historical_owner_ignored(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        room = profile.objectdb
        row = LocationOwnershipFactory(area=ward, holder_persona=PersonaFactory())
        row.ended_at = timezone.now()
        row.save()
        result = effective_owners_for_rooms([room])
        self.assertIsNone(result[room.pk])

    def test_query_budget_three_queries(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profiles = [RoomProfileFactory(area=ward) for _ in range(3)]
        rooms = [p.objectdb for p in profiles]
        LocationOwnershipFactory(area=ward, holder_persona=PersonaFactory())

        with self.assertNumQueries(3):
            effective_owners_for_rooms(rooms)


class TenanciesForRoomsTests(TestCase):
    def test_empty_rooms_returns_empty_dict(self) -> None:
        self.assertEqual(tenancies_for_rooms([]), {})

    def test_single_room_matches_singular_helper(self) -> None:
        building = AreaFactory(level=AreaLevel.BUILDING)
        profile = RoomProfileFactory(area=building)
        room = profile.objectdb
        row = LocationTenancyFactory(room_profile=profile, tenant_persona=PersonaFactory())
        result = tenancies_for_rooms([room])
        self.assertEqual(result[room.pk], [row])
        self.assertEqual(list(current_tenants(room)), result[room.pk])

    def test_includes_room_and_ancestor_area_tenancies(self) -> None:
        building = AreaFactory(level=AreaLevel.BUILDING)
        profile = RoomProfileFactory(area=building)
        room = profile.objectdb

        building_tenancy = LocationTenancyFactory(
            on_area=True, area=building, tenant_persona=PersonaFactory()
        )
        room_tenancy = LocationTenancyFactory(room_profile=profile, tenant_persona=PersonaFactory())

        result = tenancies_for_rooms([room])
        self.assertEqual(set(result[room.pk]), {building_tenancy, room_tenancy})

    def test_multiple_rooms_distinct_results(self) -> None:
        building = AreaFactory(level=AreaLevel.BUILDING)
        profile_a = RoomProfileFactory(area=building)
        profile_b = RoomProfileFactory(area=building)
        room_a, room_b = profile_a.objectdb, profile_b.objectdb

        tenancy_a = LocationTenancyFactory(room_profile=profile_a, tenant_persona=PersonaFactory())
        tenancy_b = LocationTenancyFactory(room_profile=profile_b, tenant_persona=PersonaFactory())

        result = tenancies_for_rooms([room_a, room_b])
        self.assertEqual(result[room_a.pk], [tenancy_a])
        self.assertEqual(result[room_b.pk], [tenancy_b])

    def test_expired_tenancy_excluded(self) -> None:
        building = AreaFactory(level=AreaLevel.BUILDING)
        profile = RoomProfileFactory(area=building)
        room = profile.objectdb
        LocationTenancyFactory(
            room_profile=profile,
            tenant_persona=PersonaFactory(),
            ends_at=timezone.now() - timedelta(days=1),
        )
        result = tenancies_for_rooms([room])
        self.assertEqual(result[room.pk], [])

    def test_future_ends_at_included(self) -> None:
        building = AreaFactory(level=AreaLevel.BUILDING)
        profile = RoomProfileFactory(area=building)
        room = profile.objectdb
        row = LocationTenancyFactory(
            room_profile=profile,
            tenant_persona=PersonaFactory(),
            ends_at=timezone.now() + timedelta(days=30),
        )
        result = tenancies_for_rooms([room])
        self.assertEqual(result[room.pk], [row])

    def test_room_without_profile_returns_empty_list(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()
        result = tenancies_for_rooms([room])
        self.assertEqual(result[room.pk], [])

    def test_query_budget_three_queries(self) -> None:
        building = AreaFactory(level=AreaLevel.BUILDING)
        profiles = [RoomProfileFactory(area=building) for _ in range(3)]
        rooms = [p.objectdb for p in profiles]
        LocationTenancyFactory(on_area=True, area=building, tenant_persona=PersonaFactory())

        with self.assertNumQueries(3):
            tenancies_for_rooms(rooms)


class EffectiveValuesForRoomsResonanceTests(TestCase):
    """Bulk-read tests for the resonance axis on effective_values_for_rooms."""

    def setUp(self) -> None:
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.profile_a = RoomProfileFactory(area=self.ward)
        self.profile_b = RoomProfileFactory(area=self.ward)
        self.profile_c = RoomProfileFactory(area=self.city)
        self.predari = ResonanceFactory(name="Predari")
        self.copperi = ResonanceFactory(name="Copperi")

    def test_resonance_bulk_returns_per_room_dicts(self) -> None:
        """Bulk read returns {room.pk: {resonance: value}} for each room/resonance."""
        # City-level predari modifier — visible from all three rooms
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            key_type=KeyType.RESONANCE,
            resonance=self.predari,
            value=100,
        )
        # Room-level override on profile_a for copperi
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile_a,
            key_type=KeyType.RESONANCE,
            resonance=self.copperi,
            value=1000,
        )
        rooms = [self.profile_a.objectdb, self.profile_b.objectdb, self.profile_c.objectdb]
        result = effective_values_for_rooms(rooms, resonances=[self.predari, self.copperi])

        assert result[self.profile_a.objectdb.pk][self.predari] == 100
        assert result[self.profile_a.objectdb.pk][self.copperi] == 1000
        assert result[self.profile_b.objectdb.pk][self.predari] == 100
        assert result[self.profile_b.objectdb.pk][self.copperi] == 0
        assert result[self.profile_c.objectdb.pk][self.predari] == 100
        assert result[self.profile_c.objectdb.pk][self.copperi] == 0

    def test_resonance_bulk_room_without_profile_returns_zero(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()
        result = effective_values_for_rooms([room], resonances=[self.predari])
        assert result[room.pk][self.predari] == 0

    def test_resonance_bulk_query_budget(self) -> None:
        """Resonance bulk read uses 4 queries regardless of room count."""
        rooms = [self.profile_a.objectdb, self.profile_b.objectdb, self.profile_c.objectdb]
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            key_type=KeyType.RESONANCE,
            resonance=self.predari,
            value=50,
        )
        with self.assertNumQueries(4):
            effective_values_for_rooms(rooms, resonances=[self.predari, self.copperi])

    def test_requires_exactly_one_axis_kwarg(self) -> None:
        rooms = [self.profile_a.objectdb]
        with self.assertRaises(ValueError):
            effective_values_for_rooms(rooms)
        with self.assertRaises(ValueError):
            effective_values_for_rooms(rooms, stat_keys=[StatKey.CRIME], resonances=[self.predari])

    def test_stat_path_still_works_via_effective_values_for_rooms(self) -> None:
        """Stat axis delegates to the existing effective_stats_for_rooms impl."""
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=15,
        )
        rooms = [self.profile_a.objectdb]
        result = effective_values_for_rooms(rooms, stat_keys=[StatKey.CRIME])
        assert (
            result[self.profile_a.objectdb.pk][StatKey.CRIME] == 15 + STAT_DEFAULTS[StatKey.CRIME]
        )
