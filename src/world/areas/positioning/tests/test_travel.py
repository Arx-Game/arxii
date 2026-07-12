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

    def test_query_count_stays_low_with_genuinely_multi_room_frontier(self):
        """Companion to test_query_count_scales_with_depth_not_room_count —
        that test's frontier is only ever 1 room wide at each level actually
        processed (all 20 leaves are direct children of the single origin),
        so it can't distinguish batched-per-level querying from a naive
        per-room-loop implementation for this exact graph shape. This test
        builds a genuinely multi-room frontier (5 rooms wide) at level 2, so
        the bulk `db_location_id__in=frontier` query is exercised against a
        real multi-room `frontier` set — a naive per-room-loop implementation
        would issue ~5 queries at level 2 where the batched one issues 1.
        """
        room_a = make_room(self.area, "A")
        # Level 1: 5 rooms, all direct children of A (frontier size 5 at level 2).
        level1 = [make_room(self.area, f"L1-{i}") for i in range(5)]
        for room in level1:
            make_exit(room_a, room, "path")
        # Level 2: each level-1 room has 4 children — frontier at level 2
        # processing is genuinely {L1-0, L1-1, L1-2, L1-3, L1-4}, 5 rooms.
        level2_target = None
        for room in level1:
            for i in range(4):
                leaf = make_room(self.area, f"L2-{room.db_key}-{i}")
                make_exit(room, leaf, "path")
                if level2_target is None:
                    level2_target = leaf
        # Force the target to be reached only after level 2 is processed —
        # pick the LAST leaf created under the LAST level-1 room, so BFS must
        # fully expand the 5-room level-1 frontier before finding it.
        last_room = level1[-1]
        final_leaf = make_room(self.area, "FinalTarget")
        make_exit(last_room, final_leaf, "path")

        with CaptureQueriesContext(connection) as ctx:
            route = find_route(room_a, final_leaf)

        assert route is not None
        assert len(route) == 2
        # Two BFS levels processed (level 1: frontier={A}, level 2:
        # frontier={5 level-1 rooms}) should still issue a small, level-bounded
        # query count — not one query per room in the 5-room frontier.
        assert len(ctx.captured_queries) <= 6, (
            f"expected query count bounded by BFS depth (2 levels), not frontier "
            f"width (5 rooms at level 2), got {len(ctx.captured_queries)}: "
            f"{[q['sql'] for q in ctx.captured_queries]}"
        )


class CrossAreaFindRouteTests(TestCase):
    """#2223 Decision 1: the exit graph IS the connectivity — a room-level Exit
    that crosses an Area boundary is a valid hop, with no separate Area-to-Area
    adjacency model involved. These tests replace #2163's
    `test_different_area_returns_none`, which asserted the old same-Area wall
    that this feature removes.
    """

    def setUp(self):
        self.area = AreaFactory()
        self.other_area = AreaFactory()

    def test_route_crosses_area_boundary_via_connecting_exit(self):
        room_a = make_room(self.area, "A")
        room_b = make_room(self.other_area, "B")
        exit_ab = make_exit(room_a, room_b, "east")

        route = find_route(room_a, room_b)

        assert route == [exit_ab]

    def test_multi_hop_route_crosses_boundary_partway(self):
        room_a = make_room(self.area, "A")
        room_boundary = make_room(self.area, "Boundary")
        room_c = make_room(self.other_area, "C")
        exit_a_boundary = make_exit(room_a, room_boundary, "east")
        exit_boundary_c = make_exit(room_boundary, room_c, "east")

        route = find_route(room_a, room_c)

        assert route == [exit_a_boundary, exit_boundary_c]

    def test_unlinked_areas_returns_none(self):
        # Two Areas exist, but no exit connects any room in one to any room in
        # the other — no adjacency data means no route, exactly like same-Area
        # unreachability. Areas are not connected by fiat; only exits connect rooms.
        room_a = make_room(self.area, "A")
        room_b = make_room(self.other_area, "B")

        assert find_route(room_a, room_b) is None

    def test_hop_cap_enforced_across_boundary(self):
        from django.test import override_settings

        room_a = make_room(self.area, "A")
        room_mid = make_room(self.area, "Mid")
        room_b = make_room(self.other_area, "B")
        make_exit(room_a, room_mid, "east")
        make_exit(room_mid, room_b, "east")

        with override_settings(TRAVEL_MAX_HOPS=1):
            assert find_route(room_a, room_b) is None

    def test_private_room_not_used_as_waypoint_across_boundary(self):
        room_a = make_room(self.area, "A")
        room_private = ObjectDBFactory(db_key="Private", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=room_private, defaults={"area": self.other_area, "is_public": False}
        )
        room_c = make_room(self.other_area, "C")
        make_exit(room_a, room_private, "east")
        make_exit(room_private, room_c, "east")

        assert find_route(room_a, room_c) is None
