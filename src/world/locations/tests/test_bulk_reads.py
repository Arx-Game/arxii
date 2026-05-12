from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import (
    STAT_DEFAULTS,
    LocationParentType,
    StatKey,
)
from world.locations.factories import (
    LocationStatModifierFactory,
    LocationStatOverrideFactory,
)
from world.locations.services import (
    _bulk_room_profiles_and_ancestors,
    effective_stat,
    effective_stats_for_rooms,
)


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
        result = effective_stats_for_rooms([], [StatKey.CRIME])
        self.assertEqual(result, {})

    def test_empty_stat_keys_returns_empty_per_room(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        result = effective_stats_for_rooms([room], [])
        self.assertEqual(result, {room.pk: {}})

    def test_single_room_matches_singular_helper(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        room = profile.objectdb
        LocationStatOverrideFactory(area=ward, stat_key=StatKey.CRIME, value=42)

        bulk_result = effective_stats_for_rooms([room], [StatKey.CRIME])
        singular_result = effective_stat(room, StatKey.CRIME)

        self.assertEqual(bulk_result[room.pk][StatKey.CRIME], singular_result)

    def test_multiple_rooms_distinct_results(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile_a = RoomProfileFactory(area=ward)
        profile_b = RoomProfileFactory(area=ward)
        room_a, room_b = profile_a.objectdb, profile_b.objectdb

        # Room A has a room-level override; Room B uses the ward default
        LocationStatOverrideFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=profile_a,
            stat_key=StatKey.CRIME,
            value=80,
        )

        result = effective_stats_for_rooms([room_a, room_b], [StatKey.CRIME])
        self.assertEqual(result[room_a.pk][StatKey.CRIME], 80)
        # Room B falls through to default (no override, no modifier)
        self.assertEqual(
            result[room_b.pk][StatKey.CRIME],
            effective_stat(room_b, StatKey.CRIME),
        )

    def test_room_without_profile_falls_through_to_defaults(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()

        result = effective_stats_for_rooms([room], [StatKey.CRIME, StatKey.LIGHTING])
        self.assertEqual(result[room.pk][StatKey.CRIME], STAT_DEFAULTS[StatKey.CRIME])
        self.assertEqual(result[room.pk][StatKey.LIGHTING], STAT_DEFAULTS[StatKey.LIGHTING])

    def test_query_budget_three_queries(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profiles = [RoomProfileFactory(area=ward) for _ in range(3)]
        rooms = [p.objectdb for p in profiles]
        LocationStatOverrideFactory(area=ward, stat_key=StatKey.CRIME, value=20)
        LocationStatModifierFactory(area=ward, stat_key=StatKey.NOISE, value=10)

        # Re-fetch rooms to defeat upstream caching for a clean budget read.
        rooms = [ObjectDB.objects.get(pk=r.pk) for r in rooms]

        with self.assertNumQueries(3):
            effective_stats_for_rooms(rooms, [StatKey.CRIME, StatKey.NOISE])
