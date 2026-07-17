"""Area-generic room-graph core (#2449): rooms, exit pairs, grid, BFS reachability."""

from django.test import TestCase

from evennia_extensions.models import ObjectDisplayData, RoomProfile, RoomSizeTier
from evennia_extensions.seeds import ensure_room_size_tiers
from world.areas.constants import GridOrigin
from world.areas.factories import AreaFactory
from world.areas.grid_services import (
    GridServiceError,
    cell_occupied,
    create_exit_pair,
    create_room,
    exits_for_rooms,
    exits_from_rooms,
    place_room_on_grid,
    promote_to_authored,
    stranded_rooms,
    suggest_fixture_key,
)


class CreateRoomTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_room_size_tiers()
        cls.snug = RoomSizeTier.objects.get(name="Snug")
        cls.area = AreaFactory()

    def test_creates_room_object_and_profile(self) -> None:
        profile = create_room(
            area=self.area,
            name="Sun Room",
            description="A bright little room.",
            size=self.snug,
            grid_x=1,
            grid_y=2,
            floor=1,
            origin=GridOrigin.STORY,
            fixture_key=None,
        )
        self.assertIsInstance(profile, RoomProfile)
        self.assertEqual(profile.objectdb.db_key, "Sun Room")
        self.assertEqual(profile.objectdb.db_typeclass_path, "typeclasses.rooms.Room")
        self.assertEqual(profile.area, self.area)
        self.assertEqual(profile.size, self.snug)
        self.assertEqual((profile.grid_x, profile.grid_y, profile.floor), (1, 2, 1))
        self.assertEqual(profile.origin, GridOrigin.STORY)
        self.assertIsNone(profile.fixture_key)
        display = ObjectDisplayData.objects.get(object=profile.objectdb)
        self.assertEqual(display.permanent_description, "A bright little room.")

    def test_defaults_origin_player_and_unplaced(self) -> None:
        profile = create_room(area=self.area, name="Plain Room")
        self.assertEqual(profile.origin, GridOrigin.PLAYER)
        self.assertIsNone(profile.grid_x)
        self.assertIsNone(profile.grid_y)
        self.assertEqual(profile.floor, 0)

    def test_fixture_key_round_trips(self) -> None:
        profile = create_room(
            area=self.area,
            name="Authored Room",
            origin=GridOrigin.AUTHORED,
            fixture_key="arx-city/authored-room",
        )
        self.assertEqual(profile.fixture_key, "arx-city/authored-room")


class CreateExitPairTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory()
        cls.other_area = AreaFactory()
        cls.room_a = create_room(area=cls.area, name="Room A").objectdb
        cls.room_b = create_room(area=cls.area, name="Room B").objectdb
        cls.cross_room = create_room(area=cls.other_area, name="Cross Area Room").objectdb

    def test_symmetric_exit_pair_created(self) -> None:
        forward, backward = create_exit_pair(
            name="north",
            aliases=("n",),
            reverse_name="south",
            reverse_aliases=("s",),
            room_a=self.room_a,
            room_b=self.room_b,
        )
        self.assertEqual(forward.db_location, self.room_a)
        self.assertEqual(forward.db_destination, self.room_b)
        self.assertEqual(forward.db_key, "north")
        self.assertIn("n", [a.strip().lower() for a in forward.aliases.all()])
        self.assertEqual(backward.db_location, self.room_b)
        self.assertEqual(backward.db_destination, self.room_a)
        self.assertEqual(backward.db_key, "south")
        self.assertIn("s", [a.strip().lower() for a in backward.aliases.all()])

    def test_cross_area_exit_allowed(self) -> None:
        forward, backward = create_exit_pair(
            name="portal",
            aliases=(),
            reverse_name="return portal",
            reverse_aliases=(),
            room_a=self.room_a,
            room_b=self.cross_room,
        )
        self.assertEqual(forward.db_destination, self.cross_room)
        self.assertEqual(backward.db_location, self.cross_room)
        self.assertEqual(backward.db_destination, self.room_a)


class CellOccupiedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory()

    def test_empty_cell_not_occupied(self) -> None:
        self.assertFalse(cell_occupied(self.area, 0, 0, 0))

    def test_occupied_cell_true(self) -> None:
        create_room(area=self.area, name="Occupant", grid_x=3, grid_y=4, floor=0)
        self.assertTrue(cell_occupied(self.area, 3, 4, 0))
        self.assertFalse(cell_occupied(self.area, 3, 4, 1))


class PlaceRoomOnGridTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory()

    def test_places_room_on_empty_cell(self) -> None:
        profile = create_room(area=self.area, name="Loose Room")
        place_room_on_grid(profile=profile, grid_x=2, grid_y=3, floor=1)
        profile.refresh_from_db()
        self.assertEqual((profile.grid_x, profile.grid_y, profile.floor), (2, 3, 1))

    def test_collision_raises_grid_service_error(self) -> None:
        create_room(area=self.area, name="Blocker", grid_x=0, grid_y=0, floor=0)
        mover = create_room(area=self.area, name="Mover")
        with self.assertRaises(GridServiceError) as caught:
            place_room_on_grid(profile=mover, grid_x=0, grid_y=0, floor=0)
        self.assertIn("already occupied", caught.exception.user_message)

    def test_moving_onto_own_cell_is_noop_success(self) -> None:
        profile = create_room(area=self.area, name="Static Room", grid_x=0, grid_y=0, floor=0)
        place_room_on_grid(profile=profile, grid_x=0, grid_y=0, floor=0)
        profile.refresh_from_db()
        self.assertEqual((profile.grid_x, profile.grid_y, profile.floor), (0, 0, 0))


class ExitsForRoomsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory()
        cls.other_area = AreaFactory()
        cls.room_a = create_room(area=cls.area, name="Exits Room A").objectdb
        cls.room_b = create_room(area=cls.area, name="Exits Room B").objectdb
        cls.outside_room = create_room(area=cls.other_area, name="Outside Room").objectdb

    def test_exits_for_rooms_requires_both_endpoints_in_set(self) -> None:
        create_exit_pair(
            name="north",
            aliases=(),
            reverse_name="south",
            reverse_aliases=(),
            room_a=self.room_a,
            room_b=self.room_b,
        )
        create_exit_pair(
            name="portal",
            aliases=(),
            reverse_name="return portal",
            reverse_aliases=(),
            room_a=self.room_a,
            room_b=self.outside_room,
        )
        room_ids = {self.room_a.pk, self.room_b.pk}
        internal = set(exits_for_rooms(room_ids).values_list("db_key", flat=True))
        self.assertEqual(internal, {"north", "south"})

    def test_exits_from_rooms_includes_cross_area_destinations(self) -> None:
        create_exit_pair(
            name="portal",
            aliases=(),
            reverse_name="return portal",
            reverse_aliases=(),
            room_a=self.room_a,
            room_b=self.outside_room,
        )
        room_ids = {self.room_a.pk}
        from_a = set(exits_from_rooms(room_ids).values_list("db_key", flat=True))
        self.assertIn("portal", from_a)
        self.assertNotIn("return portal", from_a)


class StrandedRoomsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory()
        cls.entry = create_room(area=cls.area, name="Entry").objectdb
        cls.middle = create_room(area=cls.area, name="Middle").objectdb
        cls.leaf = create_room(area=cls.area, name="Leaf").objectdb
        cls.entry_middle = create_exit_pair(
            name="north",
            aliases=(),
            reverse_name="south",
            reverse_aliases=(),
            room_a=cls.entry,
            room_b=cls.middle,
        )
        cls.middle_leaf = create_exit_pair(
            name="east",
            aliases=(),
            reverse_name="west",
            reverse_aliases=(),
            room_a=cls.middle,
            room_b=cls.leaf,
        )

    def _room_ids(self) -> set[int]:
        return {self.entry.pk, self.middle.pk, self.leaf.pk}

    def test_fully_connected_graph_has_no_stranded_rooms(self) -> None:
        orphaned = stranded_rooms(anchor_room_id=self.entry.pk, room_ids=self._room_ids())
        self.assertEqual(orphaned, set())

    def test_dropping_middle_room_strands_leaf(self) -> None:
        orphaned = stranded_rooms(
            anchor_room_id=self.entry.pk,
            room_ids=self._room_ids(),
            drop_room_id=self.middle.pk,
        )
        self.assertEqual(orphaned, {self.leaf.pk})

    def test_dropping_connecting_exit_strands_leaf(self) -> None:
        forward, backward = self.middle_leaf
        orphaned = stranded_rooms(
            anchor_room_id=self.entry.pk,
            room_ids=self._room_ids(),
            drop_exit_ids=frozenset({forward.pk, backward.pk}),
        )
        self.assertEqual(orphaned, {self.leaf.pk})

    def test_dropping_anchor_room_returns_empty(self) -> None:
        orphaned = stranded_rooms(
            anchor_room_id=self.entry.pk,
            room_ids=self._room_ids(),
            drop_room_id=self.entry.pk,
        )
        self.assertEqual(orphaned, set())


class PromoteToAuthoredRoomTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.authored_area = AreaFactory(origin=GridOrigin.AUTHORED, slug="arx-city")
        cls.player_area = AreaFactory(origin=GridOrigin.PLAYER)

    def test_promotes_room_in_authored_area(self) -> None:
        profile = create_room(area=self.authored_area, name="Taproom")
        promote_to_authored(room_profile=profile, key="arx-city/taproom")
        profile.refresh_from_db()
        self.assertEqual(profile.origin, GridOrigin.AUTHORED)
        self.assertEqual(profile.fixture_key, "arx-city/taproom")

    def test_room_in_player_area_raises(self) -> None:
        profile = create_room(area=self.player_area, name="Shack")
        with self.assertRaises(GridServiceError):
            promote_to_authored(room_profile=profile, key="some-area/shack")

    def test_room_with_no_area_raises(self) -> None:
        profile = create_room(area=self.authored_area, name="Floating")
        profile.area = None
        profile.save(update_fields=["area"])
        with self.assertRaises(GridServiceError):
            promote_to_authored(room_profile=profile, key="arx-city/floating")

    def test_invalid_key_format_raises(self) -> None:
        profile = create_room(area=self.authored_area, name="Bad Key Room")
        with self.assertRaises(GridServiceError):
            promote_to_authored(room_profile=profile, key="NotASlug")

    def test_rekeying_with_a_different_key_raises(self) -> None:
        profile = create_room(area=self.authored_area, name="Vault")
        promote_to_authored(room_profile=profile, key="arx-city/vault")
        with self.assertRaises(GridServiceError):
            promote_to_authored(room_profile=profile, key="arx-city/vault-renamed")

    def test_repromoting_with_same_key_is_idempotent(self) -> None:
        profile = create_room(area=self.authored_area, name="Vault")
        promote_to_authored(room_profile=profile, key="arx-city/vault")
        promote_to_authored(room_profile=profile, key="arx-city/vault")
        profile.refresh_from_db()
        self.assertEqual(profile.fixture_key, "arx-city/vault")

    def test_requires_exactly_one_target(self) -> None:
        with self.assertRaises(GridServiceError):
            promote_to_authored(key="arx-city/neither")

    def test_both_targets_given_raises(self) -> None:
        profile = create_room(area=self.authored_area, name="Both")
        with self.assertRaises(GridServiceError):
            promote_to_authored(room_profile=profile, area=self.authored_area, key="arx-city/both")


class PromoteToAuthoredAreaTests(TestCase):
    def test_promotes_area(self) -> None:
        area = AreaFactory(origin=GridOrigin.PLAYER)
        promote_to_authored(area=area, key="new-region")
        area.refresh_from_db()
        self.assertEqual(area.origin, GridOrigin.AUTHORED)
        self.assertEqual(area.slug, "new-region")

    def test_invalid_key_format_raises(self) -> None:
        area = AreaFactory(origin=GridOrigin.PLAYER)
        with self.assertRaises(GridServiceError):
            promote_to_authored(area=area, key="not/a/plain/slug")

    def test_rekeying_with_a_different_key_raises(self) -> None:
        area = AreaFactory(origin=GridOrigin.AUTHORED, slug="old-region")
        with self.assertRaises(GridServiceError):
            promote_to_authored(area=area, key="new-region")

    def test_repromoting_with_same_key_is_idempotent(self) -> None:
        area = AreaFactory(origin=GridOrigin.AUTHORED, slug="stable-region")
        promote_to_authored(area=area, key="stable-region")
        area.refresh_from_db()
        self.assertEqual(area.slug, "stable-region")


class SuggestFixtureKeyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(origin=GridOrigin.AUTHORED, slug="arx-city")

    def test_suggests_area_slug_and_slugified_name(self) -> None:
        self.assertEqual(
            suggest_fixture_key(self.area, "Golden Hart Taproom"),
            "arx-city/golden-hart-taproom",
        )

    def test_dedupes_on_collision(self) -> None:
        create_room(
            area=self.area,
            name="Taproom",
            origin=GridOrigin.AUTHORED,
            fixture_key="arx-city/taproom",
        )
        self.assertEqual(suggest_fixture_key(self.area, "Taproom"), "arx-city/taproom-2")

    def test_dedupes_past_first_collision(self) -> None:
        create_room(
            area=self.area,
            name="Taproom",
            origin=GridOrigin.AUTHORED,
            fixture_key="arx-city/taproom",
        )
        create_room(
            area=self.area,
            name="Taproom 2",
            origin=GridOrigin.AUTHORED,
            fixture_key="arx-city/taproom-2",
        )
        self.assertEqual(suggest_fixture_key(self.area, "Taproom"), "arx-city/taproom-3")
