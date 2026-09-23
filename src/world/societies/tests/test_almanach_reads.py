"""Tests for the Almanach de Catenys read payloads (#3983): the ladder and
the house document."""

from django.test import TestCase

from world.character_creation.factories import RealmFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import (
    assign_holder,
    batch_unclaimed,
    plant_rung,
    publish_house,
)
from world.societies.houses.almanach_reads import document_for_house, ladder_for_realm
from world.societies.houses.constants import TitleTier


class LadderReadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Inferna")
        cls.crown = OrganizationFactory(name="Piropa")
        cls.kingdom = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=cls.crown
        )
        cls.fervor = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Fervor", parent_title=cls.kingdom
        )
        batch_unclaimed(
            parent_title=cls.fervor, tier=TitleTier.COUNTY, count=2, baronies_per_county=1
        )
        publish_house(cls.crown)

    def test_rows_carry_state_sworn_to_demesne_and_vassals(self) -> None:
        payload = ladder_for_realm(self.realm)
        by_name = {r.name: r for r in payload.rows if r.name}
        fervor = by_name["Fervor"]
        assert fervor.state == "Unclaimed"
        assert fervor.claimable
        assert fervor.sworn_to == "Piropa"
        assert fervor.demesne == 1, "the seat barony of its seat county"
        assert fervor.vassals == 2, "two unclaimed counties beneath"
        assert payload.unclaimed_by_tier[TitleTier.COUNTY] == 2
        expected_baronies = 2 + 1 + 1  # vassal baronies + seat baronies of unclaimed rungs
        assert payload.unclaimed_by_tier[TitleTier.BARONY] == expected_baronies
        seat = next(r for r in payload.rows if r.is_seat_of == "Piropa")
        assert seat.tier == TitleTier.BARONY

    def test_founder_ladder_hides_unpublished_houses(self) -> None:
        other = OrganizationFactory(name="Solano")
        ardor = plant_rung(
            realm=self.realm,
            tier=TitleTier.COUNTY,
            name="Ardor",
            parent_title=self.kingdom,
            held_by=other,
        )
        founder = ladder_for_realm(self.realm, for_founder=True)
        assert all(r.house_name != "Solano" for r in founder.rows)
        assign_holder(ardor, other)
        publish_house(other)
        founder = ladder_for_realm(self.realm, for_founder=True)
        assert any(r.house_name == "Solano" for r in founder.rows)


class DocumentReadTests(TestCase):
    def test_document_folds_lands_and_lists_vassals(self) -> None:
        realm = RealmFactory(name="Inferna")
        crown = OrganizationFactory(name="Piropa")
        plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=crown)
        doc = document_for_house(crown, viewer=None, staff=True)
        assert doc.house["name"] == "Piropa"
        assert doc.lands["count"] == 1
        assert doc.lands["baronies"][0]["is_seat"] is True
        assert doc.realm["holds"] == "Inferna"
