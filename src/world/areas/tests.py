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
