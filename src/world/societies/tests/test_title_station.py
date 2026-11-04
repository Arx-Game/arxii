"""A title's station (seated, titular, potential), its charter and the claims on it
(#4983 slice 1, #4984): the model rules, before the services that write them."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.areas.tests.test_worldmap import tiny_map
from world.areas.worldmap.services import create_region_map, import_region_map_file, set_footprint
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import (
    assign_holder,
    charter_fief,
    chartered_extent,
    move_rung,
    plant_rung,
    record_claim,
    rung_area_for_title,
    set_pledged_liege,
    set_station,
    uncharter_fief,
    vacate_holder,
    withdraw_claim,
)
from world.societies.houses.almanach_pages import rung_document
from world.societies.houses.almanach_reads import ladder_for_realm
from world.societies.houses.constants import TitleStation, TitleTier
from world.societies.houses.models import CharteredFief, FealtyEdge, Title, TitleClaim
from world.societies.houses.services import HousesServiceError, swear_fealty


class TitleStationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Luxen")
        cls.kingdom = plant_rung(realm=cls.realm, tier=TitleTier.KINGDOM, name="Luxen")
        cls.duchy = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Brittany", parent_title=cls.kingdom
        )

    def test_a_titular_or_crown_title_is_never_claimable(self) -> None:
        self.kingdom.is_claimable = True
        with self.assertRaises(ValidationError):
            self.kingdom.full_clean()
        self.duchy.station = TitleStation.TITULAR
        self.duchy.is_claimable = True
        with self.assertRaises(ValidationError):
            self.duchy.full_clean()
        self.duchy.is_claimable = False
        self.duchy.full_clean()
        self.duchy.station = TitleStation.SEATED
        self.duchy.is_claimable = True
        self.duchy.full_clean()

    def test_half_filled_rows_fail_validation_not_with_a_crash(self) -> None:
        realm = RealmFactory(name="Forms")
        crown = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Crown")
        with self.assertRaises(ValidationError):
            CharteredFief(title=crown).full_clean()  # no fief yet: a form error, not a 500
        with self.assertRaises(ValidationError):
            TitleClaim(title=crown).full_clean()  # neither claimant nor house
        with self.assertRaises(ValidationError):
            TitleClaim(
                title=crown, claimant=CharacterSheetFactory(), house=OrganizationFactory()
            ).full_clean()

    def test_a_charter_names_lower_tiers_in_its_realm(self) -> None:
        other_realm = RealmFactory(name="Inferna")
        far_duchy = plant_rung(realm=other_realm, tier=TitleTier.DUCHY, name="Piropa")
        old_kingdom = plant_rung(realm=self.realm, tier=TitleTier.KINGDOM, name="Old Luxen")
        # a duchy chartered by two kingdoms is fine
        CharteredFief(title=self.kingdom, fief=self.duchy).full_clean()
        CharteredFief(title=old_kingdom, fief=self.duchy, basis="Before the revolt").full_clean()
        # at or above the title's tier: no
        with self.assertRaises(ValidationError):
            CharteredFief(title=self.duchy, fief=self.kingdom).full_clean()
        with self.assertRaises(ValidationError):
            CharteredFief(title=self.kingdom, fief=old_kingdom).full_clean()
        # another realm: only an empire's charter reaches that far
        with self.assertRaises(ValidationError):
            CharteredFief(title=self.kingdom, fief=far_duchy).full_clean()
        empire = plant_rung(realm=self.realm, tier=TitleTier.EMPIRE, name="The Chimeric Empire")
        CharteredFief(title=empire, fief=far_duchy).full_clean()


class ChartersClaimsAndOathsTests(TestCase):
    """The services that write a title's charter, the claims on it, its station and
    its pledged liege, and how the oath rules honour them (#4984)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Luxen")
        cls.republic_house = OrganizationFactory(name="The Republic of Luxen")
        cls.throne = OrganizationFactory(name="The Umbral Throne")
        cls.republic = plant_rung(
            realm=cls.realm,
            tier=TitleTier.KINGDOM,
            name="Republic of Luxen",
            held_by=cls.republic_house,
        )
        cls.old_crown = plant_rung(
            realm=cls.realm,
            tier=TitleTier.KINGDOM,
            name="Kingdom of Luxen",
            station=TitleStation.TITULAR,
        )
        cls.brittany = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Brittany", parent_title=cls.republic
        )
        cls.anjou = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Anjou", parent_title=cls.republic
        )
        cls.empire_realm = RealmFactory(name="Umbros")
        cls.imperial = plant_rung(
            realm=cls.empire_realm,
            tier=TitleTier.EMPIRE,
            name="The Umbral Empire",
            held_by=cls.throne,
        )

    def test_plant_rung_never_leaves_a_crown_or_titular_rung_claimable(self) -> None:
        assert not self.old_crown.is_claimable
        assert self.old_crown.station == TitleStation.TITULAR
        unheld_crown = plant_rung(realm=self.realm, tier=TitleTier.KINGDOM, name="Cinderus")
        assert not unheld_crown.is_claimable
        assert all(
            not t.is_claimable for t in Title.objects.filter(seat_domain=unheld_crown.seat_domain)
        )
        assert self.brittany.is_claimable
        potential = plant_rung(
            realm=self.realm,
            tier=TitleTier.DUCHY,
            name="",
            parent_title=self.republic,
            station=TitleStation.POTENTIAL,
        )
        assert not potential.is_claimable

    def test_charter_and_uncharter_a_fief_and_read_its_extent(self) -> None:
        region = create_region_map(name="Testland", anchor_x=0, anchor_y=0, width_cells=2)
        import_region_map_file(region=region, file_name="t.map", data=tiny_map().encode())
        set_footprint(area=rung_area_for_title(self.brittany), add=[(1, 1), (2, 1)])
        set_footprint(area=rung_area_for_title(self.anjou), add=[(5, 5)])
        charter_fief(title=self.old_crown, fief=self.brittany, basis="Before the revolt")
        charter_fief(title=self.old_crown, fief=self.anjou)
        charter_fief(title=self.imperial, fief=self.brittany, basis="Sworn to the throne")
        assert chartered_extent(self.old_crown) == {(1, 1), (2, 1), (5, 5)}
        assert chartered_extent(self.imperial) == {(1, 1), (2, 1)}
        assert chartered_extent(self.brittany) == set()
        with self.assertRaises(HousesServiceError):
            charter_fief(title=self.brittany, fief=self.republic)
        uncharter_fief(title=self.old_crown, fief=self.anjou)
        assert chartered_extent(self.old_crown) == {(1, 1), (2, 1)}
        assert [f.fief_id for f in self.old_crown.charter.all()] == [self.brittany.pk]

    def test_record_and_withdraw_a_claim_by_a_person_and_by_a_house(self) -> None:
        sharlotte = CharacterSheetFactory()
        claim = record_claim(title=self.old_crown, claimant=sharlotte, basis="The exiled queen")
        house_claim = record_claim(title=self.brittany, house=self.throne, basis="Carried")
        assert claim.claimant_id == sharlotte.pk
        assert claim.house_id is None
        assert house_claim.house_id == self.throne.pk
        with self.assertRaises(HousesServiceError):
            record_claim(title=self.old_crown, claimant=sharlotte)
        with self.assertRaises(HousesServiceError):
            record_claim(title=self.old_crown)
        withdraw_claim(claim)
        assert not TitleClaim.objects.filter(title=self.old_crown).exists()

    def test_set_station_and_pledged_liege(self) -> None:
        set_station(self.brittany, TitleStation.TITULAR)
        self.brittany.refresh_from_db()
        assert not self.brittany.is_claimable
        set_station(self.brittany, TitleStation.SEATED)
        with self.assertRaises(HousesServiceError):
            set_pledged_liege(self.brittany, self.anjou)  # a duchy is no crown
        set_pledged_liege(self.brittany, self.imperial)
        self.brittany.refresh_from_db()
        assert self.brittany.pledged_liege_id == self.imperial.pk
        set_pledged_liege(self.brittany, None)
        self.brittany.refresh_from_db()
        assert self.brittany.pledged_liege_id is None

    def test_assign_holder_swears_to_the_pledged_crown_when_it_is_held_else_containment(
        self,
    ) -> None:
        dukes = OrganizationFactory(name="House Brittany")
        set_pledged_liege(self.brittany, self.imperial)
        assign_holder(self.brittany, dukes)
        assert FealtyEdge.objects.get(vassal=dukes).liege_id == self.throne.pk
        # the pledged crown is unheld: containment decides
        counts = OrganizationFactory(name="House Anjou")
        set_pledged_liege(self.anjou, self.old_crown)
        assign_holder(self.anjou, counts)
        assert FealtyEdge.objects.get(vassal=counts).liege_id == self.republic_house.pk

    def test_vacating_the_container_keeps_a_pledged_oath(self) -> None:
        dukes = OrganizationFactory(name="House Brittany")
        set_pledged_liege(self.brittany, self.imperial)
        assign_holder(self.brittany, dukes)
        counts = OrganizationFactory(name="House Anjou")
        assign_holder(self.anjou, counts)
        vacate_holder(self.republic)
        assert FealtyEdge.objects.get(vassal=dukes).liege_id == self.throne.pk
        assert not FealtyEdge.objects.filter(vassal=counts).exists()

    def test_the_ladder_and_the_page_report_a_pledged_oath(self) -> None:
        dukes = OrganizationFactory(name="House Brittany")
        set_pledged_liege(self.brittany, self.imperial)
        assign_holder(self.brittany, dukes)
        rows = {r.title_id: r for r in ladder_for_realm(self.realm).rows}
        assert rows[self.brittany.pk].sworn_to == "The Umbral Throne (crown)"
        assert rung_document(self.brittany).title["sworn_to"] == "The Umbral Throne"
        # an unheld pledged rung says who its future holder will answer to
        set_pledged_liege(self.anjou, self.imperial)
        rows = {r.title_id: r for r in ladder_for_realm(self.realm).rows}
        assert rows[self.anjou.pk].sworn_to == "The Umbral Throne (crown)"

    def test_rehome_vassals_spares_a_pledged_oath_when_the_container_is_reseated(self) -> None:
        swear_fealty(vassal=self.republic_house, liege=self.throne)
        dukes = OrganizationFactory(name="House Brittany")
        set_pledged_liege(self.brittany, self.imperial)
        assign_holder(self.brittany, dukes)
        vacate_holder(self.republic)
        assign_holder(self.republic, self.republic_house)
        assert FealtyEdge.objects.get(vassal=dukes).liege_id == self.throne.pk

    def test_set_station_covers_the_chain_and_refuses_cleanly(self) -> None:
        set_station(self.brittany, TitleStation.TITULAR)
        chain = Title.objects.filter(seat_domain_id=self.brittany.seat_domain_id)
        assert {t.station for t in chain} == {TitleStation.TITULAR}
        assert not any(t.is_claimable for t in chain)
        inner = chain.get(tier=TitleTier.COUNTY)
        with self.assertRaises(HousesServiceError):
            set_station(inner, TitleStation.SEATED)
        self.old_crown.is_claimable = True  # forced by hand, past the model's own rule
        self.old_crown.save(update_fields=["is_claimable"])
        set_station(self.old_crown, TitleStation.SEATED)
        self.old_crown.refresh_from_db()
        assert self.old_crown.station == TitleStation.SEATED
        assert not self.old_crown.is_claimable

    def test_a_second_charter_of_the_same_fief_says_so(self) -> None:
        charter_fief(title=self.old_crown, fief=self.brittany)
        with self.assertRaises(HousesServiceError) as caught:
            charter_fief(title=self.old_crown, fief=self.brittany)
        assert caught.exception.user_message == "The charter already holds that fief."

    def test_force_move_of_a_held_duchy_reswears_it_and_spares_a_pledged_oath(self) -> None:
        cinderus_house = OrganizationFactory(name="House Cinderus")
        cinderus = plant_rung(
            realm=self.realm, tier=TitleTier.KINGDOM, name="Cinderus", held_by=cinderus_house
        )
        counts = OrganizationFactory(name="House Anjou")
        assign_holder(self.anjou, counts)
        assert FealtyEdge.objects.get(vassal=counts).liege_id == self.republic_house.pk
        with self.assertRaises(HousesServiceError):
            move_rung(self.anjou, cinderus)
        move_rung(self.anjou, cinderus, force=True)
        assert FealtyEdge.objects.get(vassal=counts).liege_id == cinderus_house.pk
        dukes = OrganizationFactory(name="House Brittany")
        set_pledged_liege(self.brittany, self.imperial)
        assign_holder(self.brittany, dukes)
        move_rung(self.brittany, cinderus, force=True)
        assert FealtyEdge.objects.get(vassal=dukes).liege_id == self.throne.pk
