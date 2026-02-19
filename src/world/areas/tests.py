from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.models import RoomProfile
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.services import get_ancestor_at_level, get_ancestry, get_effective_realm
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


class AreaPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plane = AreaFactory(name="Material Plane", level=AreaLevel.PLANE)
        cls.world = AreaFactory(name="Arvum", level=AreaLevel.WORLD, parent=cls.plane)
        cls.continent = AreaFactory(name="Arvum", level=AreaLevel.CONTINENT, parent=cls.world)
        cls.city = AreaFactory(name="Arx", level=AreaLevel.CITY, parent=cls.continent)
        cls.building = AreaFactory(
            name="The Gilded Stag", level=AreaLevel.BUILDING, parent=cls.city
        )

    def test_root_area_has_empty_path(self):
        assert self.plane.path == ""

    def test_child_path_contains_parent_pk(self):
        assert self.world.path == str(self.plane.pk)

    def test_grandchild_path_contains_ancestry(self):
        expected = f"{self.plane.pk}/{self.world.pk}"
        assert self.continent.path == expected

    def test_deep_path_contains_full_ancestry(self):
        expected = f"{self.plane.pk}/{self.world.pk}/{self.continent.pk}/{self.city.pk}"
        assert self.building.path == expected


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

    def test_room_profile_creation(self):
        profile = RoomProfile.objects.create(db_object=self.room_obj, area=self.building)
        assert profile.pk == self.room_obj.pk
        assert profile.area == self.building

    def test_room_profile_nullable_area(self):
        profile = RoomProfile.objects.create(db_object=self.room_obj, area=None)
        assert profile.area is None

    def test_room_profile_reverse_relation(self):
        RoomProfile.objects.create(db_object=self.room_obj, area=self.building)
        assert self.building.rooms.count() == 1
        assert self.building.rooms.first().db_object == self.room_obj

    def test_room_profile_cascade_on_room_delete(self):
        RoomProfile.objects.create(db_object=self.room_obj, area=self.building)
        self.room_obj.delete()
        assert RoomProfile.objects.count() == 0

    def test_room_profile_set_null_on_area_delete(self):
        standalone = AreaFactory(name="Standalone", level=AreaLevel.BUILDING)
        profile = RoomProfile.objects.create(db_object=self.room_obj, area=standalone)
        standalone.delete()
        profile.refresh_from_db()
        assert profile.area is None
