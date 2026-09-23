"""Tests for the Almanach de Catenys house services (#3983): state, publish,
demesne, estate, household, and public-belief."""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.models import LocationOwnership
from world.roster.factories import FamilyFactory, KinspersonFactory
from world.roster.models import FamilyMembership, Kinsperson, ParentageEdge
from world.societies.constants import VACANCY_BASIS_RETAINER
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import (
    HOUSEHOLD_RANK_TITLE,
    add_household_member,
    batch_unclaimed,
    claim_grants,
    describe_demesne,
    name_rung,
    open_household_position,
    plan_estate,
    plant_rung,
    publish_house,
    record_kin,
    record_public_belief,
    set_house_state,
    unpublish_house,
)
from world.societies.houses.constants import ClaimKinRelation, HouseState, TitleTier
from world.societies.houses.models import LandShape, Title
from world.societies.houses.services import HousesServiceError
from world.societies.models import OrganizationMembership, Vacancy


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

    def test_two_wards_get_a_row_each(self) -> None:
        """#3983 review I2(a): ``Vacancy`` is unique on (organization, name),
        so naming every ward "Ward" made the second ward silently take the
        first's row — the first ward vanished from the household."""
        first = KinspersonFactory(name="Marisol")
        second = KinspersonFactory(name="Corvin")
        record_kin(
            house=self.house, name="", relation=ClaimKinRelation.WARD, node=first, is_household=True
        )
        record_kin(
            house=self.house,
            name="",
            relation=ClaimKinRelation.WARD,
            node=second,
            is_household=True,
        )
        holders = set(
            Vacancy.objects.filter(organization=self.house).values_list(
                "holder_kinsperson_id", flat=True
            )
        )
        assert {first.pk, second.pk} <= holders

    def test_an_open_position_has_a_title_and_nobody_in_it(self) -> None:
        """#3983 ruling I2: a household POST is not a person. The plate's
        "Master-at-arms · position · open" is a Vacancy with no holder."""
        vacancy = open_household_position(house=self.house, position="Master-at-arms")
        assert vacancy.name == "Master-at-arms"
        assert vacancy.holder_kinsperson_id is None
        assert vacancy.count_remaining == 1
        assert vacancy.is_open
        assert vacancy.rank.name == HOUSEHOLD_RANK_TITLE
        # Re-posting the same title re-opens the same row, never a duplicate.
        again = open_household_position(house=self.house, position="Master-at-arms")
        assert again.pk == vacancy.pk

    def test_an_untitled_position_is_refused(self) -> None:
        with self.assertRaises(HousesServiceError):
            open_household_position(house=self.house, position="  ")

    def test_record_kin_refuses_a_position(self) -> None:
        """The seam is explicit: a POSITION never mints a Kinsperson."""
        with self.assertRaises(HousesServiceError):
            record_kin(
                house=self.house,
                name="Captain",
                relation=ClaimKinRelation.POSITION,
                is_household=True,
            )
        assert not Kinsperson.objects.filter(name="Captain").exists()

    def test_sheeted_household_member_gets_a_real_membership(self) -> None:
        sheet = CharacterSheetFactory()
        primary = sheet.primary_persona
        person = KinspersonFactory(sheet=sheet, name="Corvin")
        vacancy = add_household_member(house=self.house, kinsperson=person)
        membership = OrganizationMembership.objects.get(
            organization=self.house,
            persona=primary,
            left_at__isnull=True,
            exiled_at__isnull=True,
        )
        assert membership.rank.name == HOUSEHOLD_RANK_TITLE
        assert vacancy.holder_kinsperson_id == person.pk
        assert not FamilyMembership.objects.filter(kinsperson=person).exists()
        # A second call must not raise (AlreadyOrganizationMemberError guarded
        # against via active_membership_for_persona) and must not duplicate it.
        add_household_member(house=self.house, kinsperson=person)
        assert (
            OrganizationMembership.objects.filter(
                organization=self.house,
                persona=primary,
                left_at__isnull=True,
                exiled_at__isnull=True,
            ).count()
            == 1
        )

    def test_public_belief_is_separate_from_truth(self) -> None:
        person = KinspersonFactory(name="Anastasia")
        record_public_belief(person, believed_deceased=True)
        person.refresh_from_db()
        assert person.believed_deceased
        assert not person.is_deceased

    def test_record_kin_mother_of_head_gets_a_parent_edge(self) -> None:
        head, _ = record_kin(house=self.house, name="Estuosa", relation="head")
        mother, _ = record_kin(
            house=self.house, name="Fiamma", relation="mother", child=head, is_deceased=True
        )
        assert ParentageEdge.objects.filter(child=head, parent=mother).exists()


class ClaimGrantsTests(TestCase):
    """``claim_grants`` (#3983 Plan B): the claimed chain plus any loose
    baronies it swallows, top first."""

    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Ignis")
        cls.fervor = plant_rung(realm=cls.realm, tier=TitleTier.DUCHY, name="Fervor")
        cls.arsura = Title.objects.get(tier=TitleTier.COUNTY, seat_domain=cls.fervor.seat_domain)
        cls.ascua = Title.objects.get(tier=TitleTier.BARONY, seat_domain=cls.fervor.seat_domain)
        name_rung(cls.arsura, "Arsura")
        name_rung(cls.ascua, "Ascua")
        cls.loose_barony = batch_unclaimed(parent_title=cls.arsura, tier=TitleTier.BARONY, count=1)[
            0
        ]
        cls.solfatara = plant_rung(
            realm=cls.realm, tier=TitleTier.COUNTY, name="Solfatara", parent_title=cls.fervor
        )
        cls.tizon = Title.objects.get(tier=TitleTier.BARONY, seat_domain=cls.solfatara.seat_domain)
        name_rung(cls.tizon, "Tizon")

    def test_claim_grants_is_the_chain_plus_loose_baronies(self) -> None:
        grants = claim_grants(self.fervor)
        assert [t.tier for t in grants] == [
            TitleTier.DUCHY,
            TitleTier.COUNTY,
            TitleTier.BARONY,
            TitleTier.BARONY,
        ]
        assert grants[:3] == [self.fervor, self.arsura, self.ascua]
        assert grants[3].pk == self.loose_barony.pk
        assert self.tizon not in grants
        assert self.solfatara not in grants
