"""Tests for the Almanach de Catenys house services (#3983): state, publish,
demesne, estate, household, and public-belief."""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.locations.models import LocationOwnership
from world.roster.factories import FamilyFactory, KinspersonFactory
from world.roster.models import FamilyMembership
from world.societies.constants import VACANCY_BASIS_RETAINER
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import (
    HOUSEHOLD_RANK_TITLE,
    add_household_member,
    describe_demesne,
    plan_estate,
    plant_rung,
    publish_house,
    record_public_belief,
    set_house_state,
    unpublish_house,
)
from world.societies.houses.constants import HouseState, TitleTier
from world.societies.houses.models import LandShape
from world.societies.houses.services import HousesServiceError
from world.societies.models import Vacancy


class HouseServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Inferna")
        cls.house = OrganizationFactory(name="Piropa", family=FamilyFactory(name="House Piropa"))
        cls.kingdom = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=cls.house
        )
        cls.seat = cls.kingdom.seat_domain

    def test_state_and_publish(self) -> None:
        set_house_state(self.house, HouseState.IN_EXILE)
        self.house.refresh_from_db()
        assert self.house.house_state == HouseState.IN_EXILE
        publish_house(self.house)
        self.house.refresh_from_db()
        assert self.house.published_at is not None
        unpublish_house(self.house)
        self.house.refresh_from_db()
        assert self.house.published_at is None

    def test_describe_demesne_names_the_hall_distinctly(self) -> None:
        LandShape.objects.create(name="Coast")
        describe_demesne(
            domain=self.seat,
            description="Palazzos on the water.",
            hall_name="the Palazzo Ardente",
            land_shape_names=["Coast"],
        )
        self.seat.refresh_from_db()
        assert self.seat.description == "Palazzos on the water."
        assert self.seat.hall is not None
        assert self.seat.hall.level == AreaLevel.BUILDING
        assert self.seat.hall.parent == self.seat.area
        assert [s.name for s in self.seat.land_shapes.all()] == ["Coast"]
        self.seat.name = "Perdition"
        self.seat.save(update_fields=["name"])
        with self.assertRaises(HousesServiceError):
            describe_demesne(
                domain=self.seat, description="", hall_name="Perdition", land_shape_names=[]
            )

    def test_plan_estate_creates_an_area_held_by_the_house(self) -> None:
        city = AreaFactory(name="Perdition City", level=AreaLevel.CITY, realm=self.realm)
        district = AreaFactory(name="Harborside", level=AreaLevel.NEIGHBORHOOD, parent=city)
        estate = plan_estate(
            house=self.house,
            city_area=city,
            name="Casa Piropa",
            description="PLACEHOLDER",
            district=district,
        )
        assert estate.level == AreaLevel.BUILDING
        assert estate.parent == district
        assert LocationOwnership.objects.filter(
            area=estate, holder_organization=self.house, ended_at__isnull=True
        ).exists()
        unplaced = plan_estate(house=self.house, city_area=city, name="Casa Two", description="")
        assert unplaced.parent == city

    def test_household_member_is_a_retainer_vacancy(self) -> None:
        ward = KinspersonFactory(name="Marisol")
        vacancy = add_household_member(house=self.house, kinsperson=ward)
        assert isinstance(vacancy, Vacancy)
        assert vacancy.kin_node is None
        assert vacancy.kin_pool is None
        assert vacancy.basis == VACANCY_BASIS_RETAINER
        assert vacancy.holder_kinsperson_id == ward.pk
        assert vacancy.organization_id == self.house.pk
        assert vacancy.rank is not None
        assert vacancy.rank.name == HOUSEHOLD_RANK_TITLE
        assert vacancy.count_remaining == 0
        assert not FamilyMembership.objects.filter(kinsperson=ward).exists()

    def test_household_member_needs_a_family_on_the_house(self) -> None:
        landless = OrganizationFactory(name="Landless Outfit")
        ward = KinspersonFactory(name="Orphan")
        with self.assertRaises(HousesServiceError):
            add_household_member(house=landless, kinsperson=ward)

    def test_household_member_same_position_updates_not_duplicates(self) -> None:
        ward = KinspersonFactory(name="Second Call")
        first = add_household_member(house=self.house, kinsperson=ward, position="Steward")
        second = add_household_member(house=self.house, kinsperson=ward, position="Steward")
        assert first.pk == second.pk
        assert Vacancy.objects.filter(organization=self.house, name="Steward").count() == 1

    def test_public_belief_is_separate_from_truth(self) -> None:
        person = KinspersonFactory(name="Anastasia")
        record_public_belief(person, believed_deceased=True)
        person.refresh_from_db()
        assert person.believed_deceased
        assert not person.is_deceased
