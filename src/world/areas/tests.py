from django.core.exceptions import ValidationError
from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
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
