from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.models import RoomProfile
from flows.service_functions.serializers.room_state import RoomStatePayloadSerializer
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.serializers import AreaBreadcrumbSerializer
from world.areas.services import (
    get_ancestor_at_level,
    get_ancestry,
    get_descendant_areas,
    get_effective_realm,
    get_room_profile,
    get_rooms_in_area,
    reparent_area,
)
from world.realms.models import Realm


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
        cls.room_obj = ObjectDB.objects.create(
            db_key="Main Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )

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

        cls.room1 = ObjectDB.objects.create(
            db_key="Tavern Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.room2 = ObjectDB.objects.create(
            db_key="Tavern Kitchen",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.room3 = ObjectDB.objects.create(
            db_key="Dock Bar",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.room_no_area = ObjectDB.objects.create(
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
        cls.room_obj = ObjectDB.objects.create(
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
        room_obj = ObjectDB.objects.create(
            db_key="New Room",
            db_typeclass_path="typeclasses.objects.Object",
        )
        assert not RoomProfile.objects.filter(objectdb=room_obj).exists()
        profile = get_room_profile(room_obj)
        assert profile.objectdb == room_obj
        assert profile.area is None

    def test_get_room_profile_returns_existing(self):
        building = AreaFactory(name="Building", level=AreaLevel.BUILDING)
        room_obj = ObjectDB.objects.create(
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
        cls.room_obj = ObjectDB.objects.create(
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
