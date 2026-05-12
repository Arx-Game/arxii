from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.services import _bulk_room_profiles_and_ancestors


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
