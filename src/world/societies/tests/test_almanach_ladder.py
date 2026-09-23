"""Tests for the Almanach de Catenys ladder services (#3983): plant, batch,
liege by containment, re-home, tithe."""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.character_creation.factories import RealmFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import (
    assign_holder,
    batch_unclaimed,
    liege_for_title,
    name_rung,
    plant_rung,
)
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import FealtyEdge, Title
from world.societies.houses.services import HousesServiceError, add_holding, swear_fealty


class PlantRungTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Inferna", default_tithe_pct=10)
        cls.crown = OrganizationFactory(name="Piropa")
        cls.kingdom = plant_rung(
            realm=cls.realm,
            tier=TitleTier.KINGDOM,
            name="Grand Principality of Inferna",
            held_by=cls.crown,
        )

    def test_kingdom_gets_area_domain_title_and_seat_chain(self) -> None:
        area = self.kingdom.seat_domain.area
        assert self.kingdom.tier == TitleTier.KINGDOM
        assert area.level == AreaLevel.BARONY, "the seat is the barony at the bottom of the chain"
        chain = list(Title.objects.filter(seat_domain=self.kingdom.seat_domain).order_by("pk"))
        tiers = {t.tier for t in chain}
        assert tiers == {TitleTier.KINGDOM, TitleTier.DUCHY, TitleTier.COUNTY, TitleTier.BARONY}
        for t in chain:
            assert t.house_id == self.crown.pk

    def test_duchy_under_the_crown_is_unclaimed_with_its_chain(self) -> None:
        fervor = plant_rung(
            realm=self.realm, tier=TitleTier.DUCHY, name="Fervor", parent_title=self.kingdom
        )
        assert fervor.house is None
        assert fervor.is_claimable
        county = Title.objects.get(tier=TitleTier.COUNTY, seat_domain=fervor.seat_domain)
        barony = Title.objects.get(tier=TitleTier.BARONY, seat_domain=fervor.seat_domain)
        assert county.name == ""
        assert barony.name == ""
        assert barony.seat_domain.area.parent.level == AreaLevel.COUNTY
        assert fervor.seat_domain.area.level == AreaLevel.BARONY

    def test_undefined_rung_renders_area_as_undefined_and_names_later(self) -> None:
        fervor = plant_rung(
            realm=self.realm, tier=TitleTier.DUCHY, name="", parent_title=self.kingdom
        )
        duchy_area = fervor.seat_domain.area.parent.parent
        assert duchy_area.name == "Undefined"
        assert duchy_area.slug.startswith("grand-principality-of-inferna-duchy-")
        name_rung(fervor, "Fervor")
        fervor.refresh_from_db()
        duchy_area.refresh_from_db()
        assert fervor.name == "Fervor"
        assert duchy_area.name == "Fervor"
        assert duchy_area.slug == "fervor"

    def test_batch_mints_counties_each_with_a_seat_barony(self) -> None:
        fervor = plant_rung(
            realm=self.realm, tier=TitleTier.DUCHY, name="Fervor", parent_title=self.kingdom
        )
        made = batch_unclaimed(
            parent_title=fervor, tier=TitleTier.COUNTY, count=2, baronies_per_county=2
        )
        assert len(made) == 2
        for county in made:
            assert county.name == ""
            assert county.house is None
            baronies = Title.objects.filter(
                tier=TitleTier.BARONY, seat_domain__area__parent=county.seat_domain.area.parent
            )
            assert baronies.count() == 3, "the seat barony plus two vassal baronies"

    def test_liege_is_the_nearest_held_ancestor_and_rehomes_on_claim(self) -> None:
        fervor = plant_rung(
            realm=self.realm, tier=TitleTier.DUCHY, name="Fervor", parent_title=self.kingdom
        )
        solfatara = plant_rung(
            realm=self.realm, tier=TitleTier.COUNTY, name="Solfatara", parent_title=fervor
        )
        assert liege_for_title(solfatara) == self.crown
        count_house = OrganizationFactory(name="Tizon")
        assign_holder(solfatara, count_house)
        assert FealtyEdge.objects.get(vassal=count_house).liege == self.crown
        duke_house = OrganizationFactory(name="Candela")
        assign_holder(fervor, duke_house)
        assert FealtyEdge.objects.get(vassal=count_house).liege == duke_house
        assert FealtyEdge.objects.get(vassal=duke_house).liege == self.crown

    def test_swear_fealty_mints_the_realm_default_tithe(self) -> None:
        vassal = OrganizationFactory(name="Caldera")
        edge = swear_fealty(vassal=vassal, liege=self.crown)
        assert edge.obligation is not None
        assert edge.obligation.percent == 10

    def test_add_holding_refuses_an_unowned_domain(self) -> None:
        fervor = plant_rung(
            realm=self.realm, tier=TitleTier.DUCHY, name="Fervor", parent_title=self.kingdom
        )
        from world.societies.houses.factories import HoldingKindFactory

        with self.assertRaises(HousesServiceError):
            add_holding(domain=fervor.seat_domain, kind=HoldingKindFactory(), name="quay")
