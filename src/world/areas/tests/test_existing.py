from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from flows.service_functions.serializers.room_state import RoomStatePayloadSerializer
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.factories import AreaFactory
from world.areas.models import Area
from world.areas.positioning.constants import PositionKind
from world.areas.positioning.exceptions import PositionError, PositionTransitionError
from world.areas.positioning.factories import (
    ObjectPositionFactory,
    PositionEdgeFactory,
    PositionFactory,
)
from world.areas.positioning.models import ObjectPosition, Position, PositionEdge
from world.areas.positioning.services import (
    connect_positions,
    create_position,
    disconnect_positions,
    edge_between,
    force_move_to_position,
    move_to_position,
    place_in_position,
    position_of,
    reachable_positions,
    remove_position,
)
from world.areas.serializers import AreaBreadcrumbSerializer, AreaListSerializer
from world.areas.services import (
    area_grid_path,
    get_ancestor_at_level,
    get_ancestry,
    get_descendant_areas,
    get_effective_realm,
    get_room_profile,
    get_rooms_in_area,
    reparent_area,
    societies_for_scene,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import (
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.mechanics.factories import ChallengeInstanceFactory
from world.realms.models import Realm
from world.scenes.factories import SceneFactory
from world.societies.factories import SocietyFactory


class AreaModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plane = AreaFactory(name="Material Plane", level=AreaLevel.PLANE)
        cls.world = AreaFactory(name="Arvum", level=AreaLevel.WORLD, parent=cls.plane)
        cls.continent = AreaFactory(name="Arvum", level=AreaLevel.CONTINENT, parent=cls.world)
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY, parent=cls.continent)

    def test_area_creation(self):
        assert self.plane.name == "Material Plane"
        assert self.plane.level == AreaLevel.PLANE
        assert self.plane.parent is None

    def test_area_str(self):
        assert str(self.plane) == "Material Plane (Plane)"
        assert str(self.city) == "Arx (City)"

    def test_area_parent_relationship(self):
        assert self.world.parent == self.plane
        assert self.plane.children.count() == 1
        assert self.plane.children.first() == self.world

    def test_area_realm_fk(self):
        realm = Realm.objects.create(name="Test Realm")
        area = AreaFactory(name="Kingdom", level=AreaLevel.KINGDOM, realm=realm)
        assert area.realm == realm


class AreaIdentityTest(TestCase):
    def test_area_slug_natural_key_and_origin_default(self):
        area = Area.objects.create(name="Arx City", level=AreaLevel.CITY, slug="arx-city")
        self.assertEqual(area.origin, GridOrigin.PLAYER)
        self.assertEqual(Area.objects.get_by_natural_key("arx-city").pk, area.pk)
        self.assertEqual(area.natural_key(), ("arx-city",))


class AreaValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY)

    def test_child_level_must_be_lower_than_parent(self):
        bad_area = AreaFactory.build(
            name="Bad Continent", level=AreaLevel.CONTINENT, parent=self.city
        )
        with self.assertRaises(ValidationError):
            bad_area.full_clean()

    def test_same_level_as_parent_is_invalid(self):
        bad_area = AreaFactory.build(name="Bad City", level=AreaLevel.CITY, parent=self.city)
        with self.assertRaises(ValidationError):
            bad_area.full_clean()

    def test_valid_child_level_passes(self):
        area = AreaFactory.build(name="Tavern", level=AreaLevel.BUILDING, parent=self.city)
        area.full_clean()  # Should not raise

    def test_root_area_needs_no_parent(self):
        area = AreaFactory.build(name="A Plane", level=AreaLevel.PLANE, parent=None)
        area.full_clean()  # Should not raise

    def test_cycle_detection(self):
        parent = AreaFactory(name="Region A", level=AreaLevel.REGION)
        child = AreaFactory(name="City B", level=AreaLevel.CITY, parent=parent)
        parent.parent = child
        with self.assertRaises(ValidationError):
            parent.full_clean()

    def test_save_validates_level_ordering(self):
        """Saving (not just full_clean) enforces level ordering."""
        city = AreaFactory(name="City", level=AreaLevel.CITY)
        with self.assertRaises(ValidationError):
            AreaFactory(name="Bad", level=AreaLevel.CONTINENT, parent=city)


class AreaGridCoordinateTests(TestCase):
    """Model round-trip + area_grid_path for the parent-local rendering coordinates (#2223)."""

    def test_grid_coordinates_default_to_null(self):
        area = AreaFactory(name="Unplaced Ward", level=AreaLevel.WARD)
        assert area.grid_x is None
        assert area.grid_y is None

    def test_grid_coordinates_round_trip(self):
        area = AreaFactory(name="Placed Ward", level=AreaLevel.WARD, grid_x=3, grid_y=-5)
        area.refresh_from_db()
        assert area.grid_x == 3
        assert area.grid_y == -5

    def test_grid_coordinates_can_be_cleared_back_to_null(self):
        area = AreaFactory(name="Cleared Ward", level=AreaLevel.WARD, grid_x=1, grid_y=2)
        area.grid_x = None
        area.grid_y = None
        area.save()
        area.refresh_from_db()
        assert area.grid_x is None
        assert area.grid_y is None

    def test_area_grid_path_root_only(self):
        root = AreaFactory(name="Root Plane", level=AreaLevel.PLANE, grid_x=1, grid_y=2)
        assert area_grid_path(root) == [(1, 2)]

    def test_area_grid_path_three_level_mixed_set_unset(self):
        """Root has coordinates set, middle is unset, leaf is set again."""
        root = AreaFactory(name="Root Region", level=AreaLevel.REGION, grid_x=10, grid_y=20)
        middle = AreaFactory(
            name="Middle City", level=AreaLevel.CITY, parent=root, grid_x=None, grid_y=None
        )
        leaf = AreaFactory(
            name="Leaf Ward", level=AreaLevel.WARD, parent=middle, grid_x=4, grid_y=7
        )

        assert area_grid_path(leaf) == [(10, 20), (None, None), (4, 7)]

    def test_area_grid_path_all_unset(self):
        root = AreaFactory(name="Unset Root", level=AreaLevel.REGION)
        middle = AreaFactory(name="Unset Middle", level=AreaLevel.CITY, parent=root)
        leaf = AreaFactory(name="Unset Leaf", level=AreaLevel.WARD, parent=middle)

        assert area_grid_path(leaf) == [(None, None), (None, None), (None, None)]


class AreaSerializerGridCoordinateTests(TestCase):
    """AreaListSerializer exposes the grid coordinates (#2223)."""

    def test_serializer_includes_set_coordinates(self):
        area = AreaFactory(name="Serialized Ward", level=AreaLevel.WARD, grid_x=6, grid_y=-2)
        area.children_count = 0
        data = AreaListSerializer(area).data
        assert data["grid_x"] == 6
        assert data["grid_y"] == -2

    def test_serializer_includes_null_coordinates(self):
        area = AreaFactory(name="Unplaced Serialized Ward", level=AreaLevel.WARD)
        area.children_count = 0
        data = AreaListSerializer(area).data
        assert data["grid_x"] is None
        assert data["grid_y"] is None


class AreaQueryHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = Realm.objects.create(name="Arx")
        cls.plane = AreaFactory(name="Material Plane", level=AreaLevel.PLANE)
        cls.continent = AreaFactory(name="Arvum", level=AreaLevel.CONTINENT, parent=cls.plane)
        cls.kingdom = AreaFactory(
            name="Compact",
            level=AreaLevel.KINGDOM,
            parent=cls.continent,
            realm=cls.realm,
        )
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY, parent=cls.kingdom)
        cls.ward = AreaFactory(name="Upper Boroughs", level=AreaLevel.WARD, parent=cls.city)
        cls.building = AreaFactory(
            name="The Gilded Stag", level=AreaLevel.BUILDING, parent=cls.ward
        )

    def test_get_ancestry_root(self):
        result = get_ancestry(self.plane)
        assert result == [self.plane]

    def test_get_ancestry_deep(self):
        result = get_ancestry(self.building)
        assert result == [
            self.plane,
            self.continent,
            self.kingdom,
            self.city,
            self.ward,
            self.building,
        ]

    def test_get_ancestor_at_level_found(self):
        result = get_ancestor_at_level(self.building, AreaLevel.CITY)
        assert result == self.city

    def test_get_ancestor_at_level_not_found(self):
        result = get_ancestor_at_level(self.building, AreaLevel.REGION)
        assert result is None

    def test_get_ancestor_at_level_self(self):
        result = get_ancestor_at_level(self.city, AreaLevel.CITY)
        assert result == self.city

    def test_get_effective_realm_direct(self):
        result = get_effective_realm(self.kingdom)
        assert result == self.realm

    def test_get_effective_realm_inherited(self):
        result = get_effective_realm(self.building)
        assert result == self.realm

    def test_get_effective_realm_none(self):
        result = get_effective_realm(self.plane)
        assert result is None

    def test_get_effective_realm_override(self):
        other_realm = Realm.objects.create(name="Umbros")
        contested = AreaFactory(
            name="Contested Ward",
            level=AreaLevel.WARD,
            parent=self.city,
            realm=other_realm,
        )
        result = get_effective_realm(contested)
        assert result == other_realm


class RoomProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY)
        cls.building = AreaFactory(name="Tavern", level=AreaLevel.BUILDING, parent=cls.city)
        cls.room_obj = ObjectDBFactory(
            db_key="Main Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def setUp(self):
        # Flush SharedMemoryModel caches to prevent test pollution
        RoomProfile.flush_instance_cache()

    def test_room_profile_auto_created(self):
        """Room typeclass auto-creates a RoomProfile via at_object_creation."""
        profile = RoomProfile.objects.get(objectdb=self.room_obj)
        assert profile.pk == self.room_obj.pk
        assert profile.area is None

    def test_room_profile_assign_area(self):
        profile, _ = RoomProfile.objects.update_or_create(
            objectdb=self.room_obj, defaults={"area": self.building}
        )
        assert profile.area == self.building

    def test_room_profile_nullable_area(self):
        profile = RoomProfile.objects.get(objectdb=self.room_obj)
        assert profile.area is None

    def test_room_profile_reverse_relation(self):
        RoomProfile.objects.update_or_create(
            objectdb=self.room_obj, defaults={"area": self.building}
        )
        assert self.building.rooms.count() == 1
        assert self.building.rooms.first().objectdb == self.room_obj

    def test_room_profile_cascade_on_room_delete(self):
        assert RoomProfile.objects.filter(objectdb=self.room_obj).exists()
        self.room_obj.delete()
        assert not RoomProfile.objects.filter(pk=self.room_obj.pk).exists()

    def test_room_profile_set_null_on_area_delete(self):
        standalone = AreaFactory(name="Standalone", level=AreaLevel.BUILDING)
        profile, _ = RoomProfile.objects.update_or_create(
            objectdb=self.room_obj, defaults={"area": standalone}
        )
        standalone.delete()
        # Flush identity mapper cache so refresh_from_db picks up SET_NULL change
        RoomProfile.flush_instance_cache()
        profile.refresh_from_db()
        assert profile.area is None


class SubtreeQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY)
        cls.ward = AreaFactory(name="Upper Boroughs", level=AreaLevel.WARD, parent=cls.city)
        cls.neighborhood = AreaFactory(
            name="Valardin Quarter",
            level=AreaLevel.NEIGHBORHOOD,
            parent=cls.ward,
        )
        cls.building = AreaFactory(
            name="Stag Inn", level=AreaLevel.BUILDING, parent=cls.neighborhood
        )
        cls.other_ward = AreaFactory(name="Lower Boroughs", level=AreaLevel.WARD, parent=cls.city)
        cls.other_building = AreaFactory(
            name="Dockside Pub", level=AreaLevel.BUILDING, parent=cls.other_ward
        )

        cls.room1 = ObjectDBFactory(
            db_key="Tavern Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.room2 = ObjectDBFactory(
            db_key="Tavern Kitchen",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.room3 = ObjectDBFactory(
            db_key="Dock Bar",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.room_no_area = ObjectDBFactory(
            db_key="Wilderness",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        RoomProfile.objects.update_or_create(objectdb=cls.room1, defaults={"area": cls.building})
        RoomProfile.objects.update_or_create(objectdb=cls.room2, defaults={"area": cls.building})
        RoomProfile.objects.update_or_create(
            objectdb=cls.room3, defaults={"area": cls.other_building}
        )
        # room_no_area gets auto-created RoomProfile with area=None

    def test_get_descendant_areas_city(self):
        descendants = get_descendant_areas(self.city)
        assert set(descendants) == {
            self.ward,
            self.neighborhood,
            self.building,
            self.other_ward,
            self.other_building,
        }

    def test_get_descendant_areas_leaf(self):
        descendants = get_descendant_areas(self.building)
        assert descendants == []

    def test_get_rooms_in_building(self):
        rooms = get_rooms_in_area(self.building)
        room_objects = {r.objectdb for r in rooms}
        assert room_objects == {self.room1, self.room2}

    def test_get_rooms_in_city(self):
        rooms = get_rooms_in_area(self.city)
        room_objects = {r.objectdb for r in rooms}
        assert room_objects == {self.room1, self.room2, self.room3}

    def test_get_rooms_in_ward(self):
        rooms = get_rooms_in_area(self.ward)
        room_objects = {r.objectdb for r in rooms}
        assert room_objects == {self.room1, self.room2}


class ReparentingTests(TestCase):
    def test_reparent_updates_area_parent(self):
        region_a = AreaFactory(name="Region A", level=AreaLevel.REGION)
        region_b = AreaFactory(name="Region B", level=AreaLevel.REGION)
        city = AreaFactory(name="City", level=AreaLevel.CITY, parent=region_a)

        reparent_area(city, region_b)
        city.refresh_from_db()

        assert city.parent == region_b

    def test_reparent_descendants_follow_parent(self):
        """Descendants inherit ancestry from parent FK chain, no manual updates needed."""
        region_a = AreaFactory(name="Region A", level=AreaLevel.REGION)
        region_b = AreaFactory(name="Region B", level=AreaLevel.REGION)
        city = AreaFactory(name="City", level=AreaLevel.CITY, parent=region_a)
        ward = AreaFactory(name="Ward", level=AreaLevel.WARD, parent=city)
        building = AreaFactory(name="Building", level=AreaLevel.BUILDING, parent=ward)

        reparent_area(city, region_b)

        # Descendants should now show region_b in their ancestry
        ancestry = get_ancestry(building)
        assert region_b in ancestry
        assert region_a not in ancestry

    def test_reparent_validates_level(self):
        city = AreaFactory(name="City", level=AreaLevel.CITY)
        building = AreaFactory(name="Building", level=AreaLevel.BUILDING)

        with self.assertRaises(ValidationError):
            reparent_area(city, building)

    def test_reparent_to_none(self):
        region = AreaFactory(name="Region", level=AreaLevel.REGION)
        city = AreaFactory(name="City", level=AreaLevel.CITY, parent=region)
        ward = AreaFactory(name="Ward", level=AreaLevel.WARD, parent=city)

        reparent_area(city, None)
        city.refresh_from_db()

        assert city.parent is None
        # Ward's ancestry should just be city -> ward now
        ancestry = get_ancestry(ward)
        assert ancestry == [city, ward]


class RoomStateAncestryTests(TestCase):
    """Test that ancestry data is available for room state serialization."""

    @classmethod
    def setUpTestData(cls):
        cls.realm = Realm.objects.create(name="Arx", theme="arx")
        cls.continent = AreaFactory(name="Arvum", level=AreaLevel.CONTINENT)
        cls.kingdom = AreaFactory(
            name="Compact",
            level=AreaLevel.KINGDOM,
            parent=cls.continent,
            realm=cls.realm,
        )
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY, parent=cls.kingdom)
        cls.building = AreaFactory(name="The Stag", level=AreaLevel.BUILDING, parent=cls.city)
        cls.room_obj = ObjectDBFactory(
            db_key="Main Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.profile, _ = RoomProfile.objects.update_or_create(
            objectdb=cls.room_obj, defaults={"area": cls.building}
        )

    def test_serialize_ancestry(self):
        ancestry = get_ancestry(self.building)
        serializer = AreaBreadcrumbSerializer(ancestry, many=True)
        data = serializer.data
        assert len(data) == 4
        assert data[0]["name"] == "Arvum"
        assert data[0]["level"] == "Continent"
        assert data[-1]["name"] == "The Stag"
        assert data[-1]["level"] == "Building"

    def test_serialize_ancestry_includes_id(self):
        ancestry = get_ancestry(self.building)
        serializer = AreaBreadcrumbSerializer(ancestry, many=True)
        data = serializer.data
        assert data[0]["id"] == self.continent.pk
        assert data[-1]["id"] == self.building.pk


class GetRoomProfileTests(TestCase):
    def test_get_room_profile_creates_if_missing(self):
        """get_room_profile creates a RoomProfile for non-Room ObjectDB instances."""
        room_obj = ObjectDBFactory(
            db_key="New Room",
            db_typeclass_path="typeclasses.objects.Object",
        )
        assert not RoomProfile.objects.filter(objectdb=room_obj).exists()
        profile = get_room_profile(room_obj)
        assert profile.objectdb == room_obj
        assert profile.area is None

    def test_get_room_profile_returns_existing(self):
        building = AreaFactory(name="Building", level=AreaLevel.BUILDING)
        room_obj = ObjectDBFactory(
            db_key="Existing Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        # at_object_creation auto-creates profile; update it with area
        existing, _ = RoomProfile.objects.update_or_create(
            objectdb=room_obj, defaults={"area": building}
        )
        profile = get_room_profile(room_obj)
        assert profile == existing
        assert profile.area == building


class PayloadIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = Realm.objects.create(name="Arx", theme="arx")
        cls.kingdom = AreaFactory(name="Compact", level=AreaLevel.KINGDOM, realm=cls.realm)
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY, parent=cls.kingdom)
        cls.room_obj = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        RoomProfile.objects.update_or_create(objectdb=cls.room_obj, defaults={"area": cls.city})

    def test_payload_includes_ancestry_and_realm(self):
        mock_room = MagicMock()
        mock_room.obj = self.room_obj

        serializer = RoomStatePayloadSerializer(
            None,
            context={"caller": MagicMock(), "room": mock_room},
        )
        ancestry = serializer._get_ancestry(mock_room)
        realm = serializer._get_realm(mock_room)

        assert len(ancestry) == 2  # kingdom + city
        assert ancestry[0]["name"] == "Compact"
        assert ancestry[1]["name"] == "Arx"
        assert realm["name"] == "Arx"
        assert realm["theme"] == "arx"


def _make_room_in_area(area):
    """Create a room ObjectDB and point its RoomProfile at the given area."""
    room_obj = ObjectDBFactory(
        db_key="Test Room",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    RoomProfile.objects.update_or_create(objectdb=room_obj, defaults={"area": area})
    return room_obj


class SocietiesForSceneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = Realm.objects.create(name="Compact Realm")
        cls.other_realm = Realm.objects.create(name="Umbros Realm")
        cls.society_a = SocietyFactory(name="Peerage", realm=cls.realm)
        cls.society_b = SocietyFactory(name="Crownlands", realm=cls.realm)
        # A society in a different realm should never be returned.
        cls.society_other = SocietyFactory(name="Abyssal", realm=cls.other_realm)

    def setUp(self):
        RoomProfile.flush_instance_cache()

    def test_dominant_society_overrides_realm_sharers(self):
        area = AreaFactory(
            name="Dominated Ward",
            level=AreaLevel.WARD,
            realm=self.realm,
            dominant_society=self.society_a,
        )
        room = _make_room_in_area(area)
        scene = SceneFactory(location=room)

        result = societies_for_scene(scene)

        assert result == [self.society_a]

    def test_all_realm_sharers_when_no_dominant_society(self):
        area = AreaFactory(
            name="Open Ward",
            level=AreaLevel.WARD,
            realm=self.realm,
            dominant_society=None,
        )
        room = _make_room_in_area(area)
        scene = SceneFactory(location=room)

        result = societies_for_scene(scene)

        assert set(result) == {self.society_a, self.society_b}
        assert self.society_other not in result

    def test_walk_resolves_realm_from_ancestor(self):
        """#1464 walk fix: a Building-level room under a realm-bearing kingdom resolves."""
        kingdom = AreaFactory(
            name="Walk Kingdom", level=AreaLevel.KINGDOM, realm=self.realm, dominant_society=None
        )
        city = AreaFactory(name="Walk City", level=AreaLevel.CITY, parent=kingdom, realm=None)
        hall = AreaFactory(name="Walk Hall", level=AreaLevel.BUILDING, parent=city, realm=None)
        room = _make_room_in_area(hall)
        scene = SceneFactory(location=room)

        result = societies_for_scene(scene)

        assert set(result) == {self.society_a, self.society_b}

    def test_walk_nearest_dominant_society_wins(self):
        """A dominant society on a nearer ancestor beats a deeper ancestor's realm."""
        kingdom = AreaFactory(name="Dominion Kingdom", level=AreaLevel.KINGDOM, realm=self.realm)
        hall = AreaFactory(
            name="Guild Hall",
            level=AreaLevel.BUILDING,
            parent=kingdom,
            realm=None,
            dominant_society=self.society_b,
        )
        room = _make_room_in_area(hall)
        scene = SceneFactory(location=room)

        result = societies_for_scene(scene)

        assert result == [self.society_b]

    def test_no_area_returns_empty(self):
        room_obj = ObjectDBFactory(
            db_key="Placeless Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        RoomProfile.objects.update_or_create(objectdb=room_obj, defaults={"area": None})
        scene = SceneFactory(location=room_obj)

        result = societies_for_scene(scene)

        assert result == []

    def test_realmless_area_returns_empty(self):
        area = AreaFactory(
            name="Realmless Ward",
            level=AreaLevel.WARD,
            realm=None,
            dominant_society=None,
        )
        room = _make_room_in_area(area)
        scene = SceneFactory(location=room)

        result = societies_for_scene(scene)

        assert result == []

    def test_no_location_returns_empty(self):
        scene = SceneFactory(location=None)

        result = societies_for_scene(scene)

        assert result == []


class PositionModelTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="Plaza",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.room2 = ObjectDBFactory(
            db_key="Alley",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_position_unique_per_room(self):
        Position.objects.create(room=self.room, name="ground", kind=PositionKind.PRIMARY)
        with self.assertRaises(IntegrityError):
            Position.objects.create(room=self.room, name="ground", kind=PositionKind.FEATURE)

    def test_edge_rejects_self_loop(self):
        a = Position.objects.create(room=self.room, name="a_loop", kind=PositionKind.FEATURE)
        with self.assertRaises(ValidationError):
            PositionEdge(position_a=a, position_b=a).full_clean()

    def test_object_position_is_one_to_one(self):
        a = Position.objects.create(room=self.room, name="a_oto", kind=PositionKind.FEATURE)
        obj = ObjectDBFactory(
            db_key="Pat",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        ObjectPosition.objects.create(objectdb=obj, position=a)
        b = Position.objects.create(room=self.room, name="b_oto", kind=PositionKind.FEATURE)
        with self.assertRaises(IntegrityError):
            ObjectPosition.objects.create(objectdb=obj, position=b)

    def test_edge_rejects_cross_room(self):
        a = Position.objects.create(room=self.room, name="north", kind=PositionKind.FEATURE)
        b = Position.objects.create(room=self.room2, name="south", kind=PositionKind.FEATURE)
        with self.assertRaises(ValidationError):
            PositionEdge(position_a=a, position_b=b).full_clean()

    def test_edge_rejects_wrong_canonical_order(self):
        a = Position.objects.create(room=self.room, name="first", kind=PositionKind.FEATURE)
        b = Position.objects.create(room=self.room, name="second", kind=PositionKind.FEATURE)
        # Swap so that position_a_id > position_b_id (wrong canonical order)
        with self.assertRaises(ValidationError):
            PositionEdge(position_a=b, position_b=a).full_clean()


# ---------------------------------------------------------------------------
# Task 4 — authoring/query service tests
# ---------------------------------------------------------------------------


class PositionServiceAuthoringTests(TestCase):
    """Tests for create_position, remove_position, connect_positions, disconnect_positions."""

    def setUp(self):
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="ServiceRoom", nohome=True)

    def test_create_position_defaults(self):
        pos = create_position(self.room, "altar")
        assert pos.room == self.room
        assert pos.name == "altar"
        assert pos.kind == PositionKind.FEATURE
        assert pos.description == ""

    def test_create_position_with_kind(self):
        pos = create_position(self.room, "ground", kind=PositionKind.PRIMARY)
        assert pos.kind == PositionKind.PRIMARY

    def test_remove_position_deletes_it(self):
        pos = create_position(self.room, "to_remove")
        pk = pos.pk
        remove_position(pos)
        assert not Position.objects.filter(pk=pk).exists()

    def test_connect_positions_canonical_order(self):
        """connect_positions always puts smaller pk as position_a."""
        a = create_position(self.room, "alpha")
        b = create_position(self.room, "beta")
        # Pass in reverse order; service must swap.
        edge = connect_positions(b, a)
        assert edge.position_a_id < edge.position_b_id
        assert edge.position_a in (a, b)
        # Canonical: smaller pk is position_a
        lo, hi = (a, b) if a.pk < b.pk else (b, a)
        assert edge.position_a == lo
        assert edge.position_b == hi

    def test_connect_positions_natural_order(self):
        """connect_positions works when a already has a smaller pk."""
        a = create_position(self.room, "first")
        b = create_position(self.room, "second")
        if a.pk > b.pk:
            a, b = b, a
        edge = connect_positions(a, b)
        assert edge.position_a == a
        assert edge.position_b == b

    def test_disconnect_positions_removes_edge(self):
        a = create_position(self.room, "da")
        b = create_position(self.room, "db")
        connect_positions(a, b)
        disconnect_positions(a, b)
        assert edge_between(a, b) is None

    def test_disconnect_positions_order_independent(self):
        a = create_position(self.room, "oa")
        b = create_position(self.room, "ob")
        connect_positions(a, b)
        disconnect_positions(b, a)  # reversed args
        assert edge_between(a, b) is None


class PositionQueryServiceTests(TestCase):
    """Tests for edge_between, position_of, reachable_positions."""

    def setUp(self):
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="QueryRoom", nohome=True)
        self.a = create_position(self.room, "node_a")
        self.b = create_position(self.room, "node_b")
        self.c = create_position(self.room, "node_c")
        self.d = create_position(self.room, "node_d")  # impassable edge to a
        self.e = create_position(self.room, "node_e")  # gated edge to a
        # a–b open, b–c open → a can reach c via b
        self.ab = connect_positions(self.a, self.b, is_passable=True)
        self.bc = connect_positions(self.b, self.c, is_passable=True)
        # a–d impassable
        self.ad = connect_positions(self.a, self.d, is_passable=False)
        # a–e gated
        self.ae = connect_positions(self.a, self.e, is_passable=True)
        self.challenge = ChallengeInstanceFactory(location=self.room, target_object=self.room)
        self.ae.gating_challenge = self.challenge
        self.ae.save()
        # Character placed at a
        self.char = CharacterFactory(location=self.room)
        ObjectPosition.objects.create(objectdb=self.char, position=self.a)

    def test_edge_between_canonical(self):
        assert edge_between(self.a, self.b) == self.ab

    def test_edge_between_reversed_args(self):
        assert edge_between(self.b, self.a) == self.ab

    def test_edge_between_none_when_not_connected(self):
        assert edge_between(self.a, self.c) is None

    def test_position_of_returns_current(self):
        assert position_of(self.char) == self.a

    def test_position_of_returns_none_when_unplaced(self):
        other = CharacterFactory(location=self.room)
        assert position_of(other) is None

    def test_reachable_positions_multi_hop(self):
        """a→b and b→c are open; c should be reachable from a."""
        reachable = reachable_positions(self.char)
        assert self.b in reachable
        assert self.c in reachable

    def test_reachable_positions_excludes_impassable(self):
        reachable = reachable_positions(self.char)
        assert self.d not in reachable

    def test_reachable_positions_excludes_gated(self):
        """An edge with an ACTIVE gating challenge is not crossable."""
        # self.challenge has is_active=True (ChallengeInstanceFactory default)
        reachable = reachable_positions(self.char)
        assert self.e not in reachable

    def test_reachable_positions_includes_inactive_gating_challenge(self):
        """An edge with an INACTIVE gating challenge IS crossable (spec: only active blocks)."""
        f = create_position(self.room, "node_f")
        af_edge = connect_positions(self.a, f, is_passable=True)
        inactive_challenge = ChallengeInstanceFactory(
            location=self.room, target_object=self.room, is_active=False
        )
        af_edge.gating_challenge = inactive_challenge
        af_edge.save()
        reachable = reachable_positions(self.char)
        assert f in reachable

    def test_reachable_positions_excludes_active_gating_challenge(self):
        """Confirm: when is_active flips True on an edge's challenge, that edge is blocked."""
        g = create_position(self.room, "node_g")
        ag_edge = connect_positions(self.a, g, is_passable=True)
        active_challenge = ChallengeInstanceFactory(
            location=self.room, target_object=self.room, is_active=True
        )
        ag_edge.gating_challenge = active_challenge
        ag_edge.save()
        reachable = reachable_positions(self.char)
        assert g not in reachable

    def test_reachable_positions_empty_when_unplaced(self):
        other = CharacterFactory(location=self.room)
        assert reachable_positions(other) == set()


# ---------------------------------------------------------------------------
# Task 5 — placement + movement service tests
# ---------------------------------------------------------------------------


class PlaceInPositionTests(TestCase):
    """Tests for place_in_position."""

    def setUp(self):
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="PlaceRoom", nohome=True)
        self.room2 = create_object("typeclasses.rooms.Room", key="PlaceRoom2", nohome=True)
        self.pos = create_position(self.room, "floor")
        self.char = CharacterFactory(location=self.room)

    def test_place_in_position_success(self):
        op = place_in_position(self.char, self.pos)
        assert op.position == self.pos
        assert position_of(self.char) == self.pos

    def test_place_in_position_cross_room_raises(self):
        other_pos = create_position(self.room2, "altar")
        with self.assertRaises(PositionError):
            place_in_position(self.char, other_pos)

    def test_place_in_position_is_idempotent(self):
        """Calling twice moves the occupancy without error."""
        pos2 = create_position(self.room, "balcony")
        place_in_position(self.char, self.pos)
        place_in_position(self.char, pos2)
        assert position_of(self.char) == pos2


class MoveToPositionTests(TestCase):
    """Tests for move_to_position — all six failure paths + success."""

    def setUp(self):
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="MoveRoom", nohome=True)
        self.room2 = create_object("typeclasses.rooms.Room", key="MoveRoom2", nohome=True)
        self.ground = create_position(self.room, "ground", kind=PositionKind.PRIMARY)
        self.balcony = create_position(self.room, "balcony")
        self.pit = create_position(self.room, "pit")
        self.guarded = create_position(self.room, "guarded")
        self.island = create_position(self.room, "island")  # no edge to ground
        self.other_pos = create_position(self.room2, "other_room_pos")
        # ground–balcony: open edge
        self.gb_edge = connect_positions(self.ground, self.balcony, is_passable=True)
        # ground–pit: impassable
        self.gp_edge = connect_positions(self.ground, self.pit, is_passable=False)
        # ground–guarded: gated
        self.gg_edge = connect_positions(self.ground, self.guarded, is_passable=True)
        self.challenge = ChallengeInstanceFactory(location=self.room, target_object=self.room)
        self.gg_edge.gating_challenge = self.challenge
        self.gg_edge.save()

        self.char = CharacterFactory(location=self.room)
        place_in_position(self.char, self.ground)

    def test_move_success(self):
        op = move_to_position(self.char, self.balcony)
        assert op.position == self.balcony
        assert position_of(self.char) == self.balcony

    def test_move_fails_cross_room(self):
        with self.assertRaises(PositionTransitionError) as ctx:
            move_to_position(self.char, self.other_pos)
        assert "not in this room" in ctx.exception.user_message

    def test_move_fails_when_unplaced(self):
        unplaced = CharacterFactory(location=self.room)
        with self.assertRaises(PositionTransitionError) as ctx:
            move_to_position(unplaced, self.balcony)
        assert "not placed" in ctx.exception.user_message

    def test_move_fails_no_edge(self):
        with self.assertRaises(PositionTransitionError) as ctx:
            move_to_position(self.char, self.island)
        assert "no path" in ctx.exception.user_message

    def test_move_fails_impassable(self):
        with self.assertRaises(PositionTransitionError) as ctx:
            move_to_position(self.char, self.pit)
        assert "blocked" in ctx.exception.user_message

    def test_move_fails_gated(self):
        with self.assertRaises(PositionTransitionError) as ctx:
            move_to_position(self.char, self.guarded)
        assert "getting past" in ctx.exception.user_message

    def test_move_fails_immobilized(self):
        """A character with MOVEMENT = 0 cannot move voluntarily.

        Sets up a CapabilityType named MOVEMENT (FoundationalCapability.MOVEMENT),
        then zeroes it via a condition capability effect that applies -100.
        """
        # Ensure the MOVEMENT CapabilityType exists with innate_baseline=1
        cap, _ = CapabilityType.objects.get_or_create(
            name=FoundationalCapability.MOVEMENT,
            defaults={"innate_baseline": 1, "description": "Locomotion capability"},
        )
        # Create a CharacterSheet for self.char (needed by conditions system)
        CharacterSheetFactory(character=self.char)

        # Condition that zeroes MOVEMENT
        template = ConditionTemplateFactory(name="immobilized_test")
        ConditionCapabilityEffectFactory(condition=template, capability=cap, value=-100)
        apply_condition(target=self.char, condition=template)

        with self.assertRaises(PositionTransitionError) as ctx:
            move_to_position(self.char, self.balcony)
        assert "cannot move" in ctx.exception.user_message

    def test_force_move_bypasses_gate(self):
        """force_move_to_position succeeds on a gated edge."""
        op = force_move_to_position(self.char, self.guarded)
        assert op.position == self.guarded

    def test_force_move_bypasses_impassable(self):
        """force_move_to_position succeeds even on an impassable edge."""
        op = force_move_to_position(self.char, self.pit)
        assert op.position == self.pit

    def test_force_move_no_edge_required(self):
        """force_move_to_position works even when no edge exists."""
        op = force_move_to_position(self.char, self.island)
        assert op.position == self.island

    def test_force_move_fails_cross_room(self):
        with self.assertRaises(PositionError):
            force_move_to_position(self.char, self.other_pos)


# ---------------------------------------------------------------------------
# Task 6 — factory tests
# ---------------------------------------------------------------------------


class PositionFactoryTests(TestCase):
    """Tests for PositionFactory, PositionEdgeFactory, ObjectPositionFactory."""

    def test_position_factory_default(self):
        pos = PositionFactory()
        assert pos.pk is not None
        assert pos.room is not None
        assert pos.kind == PositionKind.FEATURE

    def test_position_factory_shared_room(self):
        from evennia import create_object

        room = create_object("typeclasses.rooms.Room", key="SharedRoom", nohome=True)
        a = PositionFactory(room=room, name="north")
        b = PositionFactory(room=room, name="south")
        assert a.room == b.room

    def test_position_edge_factory_canonical_order(self):
        """PositionEdgeFactory always saves with position_a.pk < position_b.pk."""
        edge = PositionEdgeFactory()
        assert edge.position_a_id < edge.position_b_id

    def test_position_edge_factory_swap_branch(self):
        """PositionEdgeFactory swaps a/b when passed higher-pk as position_a."""
        from evennia import create_object

        room = create_object("typeclasses.rooms.Room", key="SwapRoom", nohome=True)
        pos_first = PositionFactory(room=room, name="first")
        pos_second = PositionFactory(room=room, name="second")
        # Ensure pos_second has a higher pk (they are inserted in order, so this holds)
        higher, lower = (
            (pos_second, pos_first) if pos_second.pk > pos_first.pk else (pos_first, pos_second)
        )
        edge = PositionEdgeFactory(position_a=higher, position_b=lower)
        assert edge.position_a_id < edge.position_b_id

    def test_position_edge_factory_same_room(self):
        edge = PositionEdgeFactory()
        assert edge.position_a.room == edge.position_b.room

    def test_object_position_factory(self):
        op = ObjectPositionFactory()
        assert op.pk is not None
        assert op.position is not None
        assert op.objectdb is not None


# ---------------------------------------------------------------------------
# Task 9 — cross-cutting integration test (social scene + combat)
# ---------------------------------------------------------------------------


class PositioningIntegrationTests(TestCase):
    """Integration test: one room's positions exercised across a social scene and a combat.

    Room layout:
      ground (PRIMARY) — open edge → balcony (FEATURE)
      ground (PRIMARY) — impassable edge → pit (FEATURE)

    Social scene:
      - Two characters placed via place_in_position; positions asserted.
      - One character moves ground→balcony via move_to_position.
      - reachable_positions for the stationary character excludes pit.

    Combat reading the same positions:
      - CombatEncounter in the same room.
      - CombatParticipant whose character is placed at ground.
      - CombatOpponent whose NPC objectdb is placed at balcony.
      - current_position on fresh instances resolves to the same Position rows.

    Failure + bypass:
      - move_to_position across the impassable ground↔pit edge raises PositionTransitionError.
      - force_move_to_position to pit succeeds.
    """

    def setUp(self) -> None:
        from evennia import create_object

        from world.combat.constants import OpponentTier
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.combat.models import CombatOpponent
        from world.combat.typeclasses.combat_npc import CombatNPC

        # --- room + positions ---
        self.room = create_object("typeclasses.rooms.Room", key="Test Arena", nohome=True)
        self.ground = create_position(self.room, "ground", kind=PositionKind.PRIMARY)
        self.balcony = create_position(self.room, "balcony", kind=PositionKind.FEATURE)
        self.pit = create_position(self.room, "pit", kind=PositionKind.FEATURE)

        # Open edge: ground ↔ balcony
        connect_positions(self.ground, self.balcony, is_passable=True)
        # Impassable edge: ground ↔ pit
        connect_positions(self.ground, self.pit, is_passable=False)

        # --- social characters: two characters in the room ---
        self.char_a = CharacterFactory(location=self.room)
        self.char_b = CharacterFactory(location=self.room)

        # --- combat: encounter in the same room ---
        self.encounter = CombatEncounterFactory(room=self.room)

        # Participant: char_b (already in room); give it a sheet
        self.sheet_b = CharacterSheetFactory()
        self.sheet_b.character.location = self.room
        self.sheet_b.character.save()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet_b
        )

        # Opponent: a CombatNPC in the same room
        self.npc = create_object(CombatNPC, key="Arena Guard", location=self.room, nohome=True)
        self.opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Arena Guard",
            health=50,
            max_health=50,
            objectdb=self.npc,
            objectdb_is_ephemeral=True,
        )

    # -- Social scene assertions --

    def test_place_in_position_asserts_position_of(self):
        """place_in_position + position_of round-trips correctly for both characters."""
        place_in_position(self.char_a, self.ground)
        place_in_position(self.char_b, self.balcony)
        assert position_of(self.char_a) == self.ground
        assert position_of(self.char_b) == self.balcony

    def test_move_to_position_updates_occupancy(self):
        """Moving char_a from ground to balcony updates position_of."""
        place_in_position(self.char_a, self.ground)
        move_to_position(self.char_a, self.balcony)
        assert position_of(self.char_a) == self.balcony

    def test_reachable_positions_excludes_pit(self):
        """After char_a moves to balcony, pit is not reachable from ground for char_b.

        char_b remains at ground; ground→pit edge is impassable so pit is excluded.
        """
        place_in_position(self.char_a, self.ground)
        place_in_position(self.char_b, self.ground)
        move_to_position(self.char_a, self.balcony)
        reachable = reachable_positions(self.char_b)
        assert self.pit not in reachable
        assert self.balcony in reachable

    # -- Combat current_position assertions --

    def test_combat_participant_current_position(self):
        """CombatParticipant.current_position resolves to the placed Position."""
        from world.combat.models import CombatParticipant

        place_in_position(self.sheet_b.character, self.ground)
        # Fresh instance so cached_property isn't inherited from setUp.
        fresh = CombatParticipant.objects.get(pk=self.participant.pk)
        assert fresh.current_position == self.ground

    def test_combat_opponent_current_position(self):
        """CombatOpponent.current_position resolves to the placed Position."""
        from world.combat.models import CombatOpponent

        place_in_position(self.npc, self.balcony)
        fresh = CombatOpponent.objects.get(pk=self.opponent.pk)
        assert fresh.current_position == self.balcony

    def test_participant_and_opponent_same_position_rows(self):
        """Participant at ground and opponent at balcony resolve to the correct distinct rows."""
        from world.combat.models import CombatOpponent, CombatParticipant

        place_in_position(self.sheet_b.character, self.ground)
        place_in_position(self.npc, self.balcony)
        fresh_participant = CombatParticipant.objects.get(pk=self.participant.pk)
        fresh_opponent = CombatOpponent.objects.get(pk=self.opponent.pk)
        assert fresh_participant.current_position == self.ground
        assert fresh_opponent.current_position == self.balcony
        assert fresh_participant.current_position != fresh_opponent.current_position

    # -- Failure + bypass --

    def test_move_to_impassable_raises_position_transition_error(self):
        """move_to_position across the impassable ground↔pit edge raises PositionTransitionError."""
        place_in_position(self.char_a, self.ground)
        with self.assertRaises(PositionTransitionError) as ctx:
            move_to_position(self.char_a, self.pit)
        assert "blocked" in ctx.exception.user_message

    def test_force_move_to_pit_succeeds(self):
        """force_move_to_position to pit bypasses the impassable edge check."""
        place_in_position(self.char_a, self.ground)
        op = force_move_to_position(self.char_a, self.pit)
        assert op.position == self.pit
        assert position_of(self.char_a) == self.pit
