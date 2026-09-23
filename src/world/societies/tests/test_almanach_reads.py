"""Tests for the Almanach de Catenys read payloads (#3983): the ladder and
the house document."""

from django.test import TestCase

from world.character_creation.factories import RealmFactory
from world.roster.factories import FamilyFactory, KinspersonFactory
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.houses.almanach import (
    add_household_member,
    assign_holder,
    batch_unclaimed,
    name_rung,
    plant_rung,
    publish_house,
)
from world.societies.houses.almanach_reads import document_for_house, ladder_for_realm
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import Title


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
        # Fervor's own internal chain member (unnamed by plant_rung) — named
        # here so a chain-member row (not a chain top) can be asserted on.
        cls.arsura = Title.objects.get(tier=TitleTier.COUNTY, seat_domain=cls.fervor.seat_domain)
        name_rung(cls.arsura, "Arsura")

    def test_rows_carry_state_sworn_to_demesne_and_vassals(self) -> None:
        payload = ladder_for_realm(self.realm)
        by_name = {r.name: r for r in payload.rows if r.name}
        fervor = by_name["Fervor"]
        arsura = by_name["Arsura"]
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
        # comes_with: a chain member reports its chain top's name; the top
        # itself reports "".
        assert arsura.comes_with == "Fervor"
        assert fervor.comes_with == ""
        # seat_domain_id: every title on one chain shares the same value.
        assert arsura.seat_domain_id == fervor.seat_domain_id
        chain_rows = [r for r in payload.rows if r.seat_domain_id == fervor.seat_domain_id]
        assert len(chain_rows) == 3, "Fervor's duchy, county (Arsura) and barony"

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

    def test_household_lists_retainers_and_excludes_kin_vacancies(self) -> None:
        realm = RealmFactory(name="Inferna")
        family = FamilyFactory(name="House Piropa")
        crown = OrganizationFactory(name="Piropa", family=family)
        plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=crown)
        ward = KinspersonFactory(name="Marisol")
        ward_vacancy = add_household_member(house=crown, kinsperson=ward)
        kin = KinspersonFactory(name="Cousin", family=family)
        VacancyFactory(
            organization=crown, name="Cousin's Claim", rank=ward_vacancy.rank, kin_node=kin
        )
        doc = document_for_house(crown, viewer=None, staff=True)
        holder_names = {row["holder_name"] for row in doc.household}
        positions = {row["position"] for row in doc.household}
        assert "Marisol" in holder_names
        assert "Cousin's Claim" not in positions

    def test_realm_demesne_and_vassals_reach_beyond_the_top_chain(self) -> None:
        realm = RealmFactory(name="Inferna")
        crown = OrganizationFactory(name="Piropa")
        other = OrganizationFactory(name="Solano")
        kingdom = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=crown)
        # Plant the county unclaimed and Seawatch under it (so Seawatch's own
        # liege walk resolves straight past the unclaimed county to the
        # crown, matching held_by=crown with no swear_fealty call at all),
        # then seat "other" on the county directly on the Title rows. Going
        # through assign_holder here would call swear_fealty(vassal=crown,
        # liege=other) - a genuine cycle (other's own liege is already crown
        # from the county's own creation), correctly refused by the write
        # side's cycle guard (#3983 Task 1-3) - and orthogonal to what this
        # read-layer test exercises.
        county = plant_rung(
            realm=realm, tier=TitleTier.COUNTY, name="Ardor", parent_title=kingdom, held_by=None
        )
        plant_rung(
            realm=realm,
            tier=TitleTier.BARONY,
            name="Seawatch",
            parent_title=county,
            held_by=crown,
        )
        for member in Title.objects.filter(seat_domain_id=county.seat_domain_id):
            member.house = other
            member.is_claimable = False
            member.save(update_fields=["house", "is_claimable"])

        doc = document_for_house(crown, viewer=None, staff=True)
        demesne_names = {row["name"] for row in doc.realm["demesne"]}
        assert "Seawatch" in demesne_names, "a barony held directly inside a vassal's county"
        assert len(doc.realm["vassals"]) == 1, "the vassal house, once"
        assert doc.realm["vassals"][0]["held_by"] == "Solano"
