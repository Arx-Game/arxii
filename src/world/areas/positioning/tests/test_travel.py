"""Tests for find_route (#2163) — frontier-batched BFS over the room/exit graph."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.areas.factories import AreaFactory
from world.areas.positioning.travel import find_route


def make_room(area, key="Room"):
    # typeclasses.rooms.Room.at_object_creation() already auto-creates a bare
    # RoomProfile via get_or_create — update_or_create (not create) applies our
    # area/is_public onto that existing row instead of colliding with it.
    room = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(objectdb=room, defaults={"area": area, "is_public": True})
    return room


def make_exit(location, destination, key="exit"):
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.exits.Exit",
        location=location,
        destination=destination,
    )


class FindRouteTests(TestCase):
    def setUp(self):
        self.area = AreaFactory()
        self.other_area = AreaFactory()

    def test_direct_route_one_hop(self):
        room_a = make_room(self.area, "A")
        room_b = make_room(self.area, "B")
        exit_ab = make_exit(room_a, room_b, "east")

        route = find_route(room_a, room_b)

        assert route == [exit_ab]

    def test_multi_hop_route(self):
        room_a = make_room(self.area, "A")
        room_b = make_room(self.area, "B")
        room_c = make_room(self.area, "C")
        exit_ab = make_exit(room_a, room_b, "east")
        exit_bc = make_exit(room_b, room_c, "east")

        route = find_route(room_a, room_c)

        assert route == [exit_ab, exit_bc]

    def test_no_route_returns_none(self):
        room_a = make_room(self.area, "A")
        room_b = make_room(self.area, "B")
        # No exit connects them.

        assert find_route(room_a, room_b) is None

    def test_different_area_returns_none(self):
        room_a = make_room(self.area, "A")
        room_b = make_room(self.other_area, "B")
        make_exit(room_a, room_b, "east")

        assert find_route(room_a, room_b) is None

    def test_destination_not_public_returns_none(self):
        room_a = make_room(self.area, "A")
        room_b = ObjectDBFactory(db_key="Private", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=room_b, defaults={"area": self.area, "is_public": False}
        )
        make_exit(room_a, room_b, "east")

        assert find_route(room_a, room_b) is None

    def test_private_room_not_used_as_waypoint(self):
        room_a = make_room(self.area, "A")
        room_private = ObjectDBFactory(db_key="Private", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=room_private, defaults={"area": self.area, "is_public": False}
        )
        room_c = make_room(self.area, "C")
        make_exit(room_a, room_private, "east")
        make_exit(room_private, room_c, "east")
        # No public path from A to C exists — the only path runs through a private room.

        assert find_route(room_a, room_c) is None

    def test_hop_cap_exceeded_returns_none(self):
        from django.test import override_settings

        rooms = [make_room(self.area, f"R{i}") for i in range(5)]
        for i in range(4):
            make_exit(rooms[i], rooms[i + 1], "east")

        with override_settings(TRAVEL_MAX_HOPS=2):
            assert find_route(rooms[0], rooms[4]) is None

    def test_query_count_scales_with_depth_not_room_count(self):
        """Load-bearing test for the query-cost constraint (#2163 Decision 7).

        A naive per-room BFS issues one query per room visited. This test builds
        a wide-but-shallow graph (many rooms, few hops) and asserts the query
        count stays bounded by hop depth, not room count — proving the frontier
        batching is real, not accidental.
        """
        room_a = make_room(self.area, "A")
        # 20 rooms all directly reachable from A in one hop each (wide frontier).
        leaves = [make_room(self.area, f"Leaf{i}") for i in range(20)]
        for leaf in leaves:
            make_exit(room_a, leaf, "path")
        target = leaves[-1]

        with CaptureQueriesContext(connection) as ctx:
            route = find_route(room_a, target)

        assert route is not None
        # One level of BFS (frontier={A}) should issue O(1) queries, not
        # O(20) — a naive per-room implementation would issue ~20 queries
        # for the 20-room frontier fetched here; batching keeps this small.
        assert len(ctx.captured_queries) <= 5, (
            f"expected a small, depth-bounded query count, got "
            f"{len(ctx.captured_queries)}: {[q['sql'] for q in ctx.captured_queries]}"
        )
