"""Charters, claims and the pledged liege (#4983 slice 1, #4984): staff record a
dormant kingdom's charter and a queen's claim through the web dispatch, pledge a duchy
to a crown, and define a house there; a player is refused; CG's undefined-house picker
never lists a crown, a titular rung or a seat chain's inner rung."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import assign_holder, plant_rung
from world.societies.houses.almanach_reads import ladder_for_realm
from world.societies.houses.constants import TitleStation, TitleTier
from world.societies.houses.models import FealtyEdge, Title


class ChartersAndClaimsJourney(JourneyCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Luxen")
        cls.throne = OrganizationFactory(name="The Umbral Throne")
        cls.empire_realm = RealmFactory(name="Umbros")
        cls.imperial = plant_rung(
            realm=cls.empire_realm,
            tier=TitleTier.EMPIRE,
            name="The Umbral Empire",
            held_by=cls.throne,
        )
        cls.republic = plant_rung(realm=cls.realm, tier=TitleTier.KINGDOM, name="Republic of Luxen")
        cls.brittany = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Brittany", parent_title=cls.republic
        )
        cls.anjou = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Anjou", parent_title=cls.republic
        )

    def setUp(self) -> None:
        super().setUp()
        room = self.make_room("The Map Room")
        self.staff = self.make_player("Apostate", room=room)
        account = self.account_of(self.staff)
        account.is_staff = True
        account.save()
        self.player = self.make_player("Hobb", room=room)

    def test_a_dormant_crown_is_chartered_claimed_and_read_back(self) -> None:
        planted = self.web(
            self.staff,
            "almanach_plant_rung",
            realm_id=self.realm.pk,
            tier=TitleTier.KINGDOM,
            name="Kingdom of Luxen",
        )
        assert planted.detail.success, planted.detail.message
        old_crown = Title.objects.get(pk=planted.detail.data["title_id"])
        told = self.web(
            self.staff,
            "almanach_set_station",
            title_id=old_crown.pk,
            station=TitleStation.TITULAR,
        )
        assert told.detail.success, told.detail.message
        for fief in (self.brittany, self.anjou):
            charted = self.web(
                self.staff,
                "almanach_charter_fief",
                title_id=old_crown.pk,
                fief_title_id=fief.pk,
                basis="Before the revolt",
            )
            assert charted.detail.success, charted.detail.message
        sharlotte = CharacterSheetFactory()
        claimed = self.web(
            self.staff,
            "almanach_record_claim",
            title_id=old_crown.pk,
            sheet_id=sharlotte.pk,
            basis="The exiled queen",
        )
        assert claimed.detail.success, claimed.detail.message
        rows = {r.title_id: r for r in ladder_for_realm(self.realm).rows}
        assert rows[old_crown.pk].state == "Titular"
        assert not rows[old_crown.pk].claimable
        assert rows[old_crown.pk].claimant_name == sharlotte.character.key
        # the Almanach title page says what the charter holds and who claims it
        page = self.api(self.account_of(self.staff)).get(
            f"/api/almanach/titles/{old_crown.pk}/document/"
        )
        assert page.status_code == 200, page.content
        assert [f["name"] for f in page.data["chartered_fiefs"]] == ["Anjou", "Brittany"]
        assert page.data["claims"][0]["basis"] == "The exiled queen"
        assert page.data["title"]["station"] == TitleStation.TITULAR
        assert page.data["chain"][0]["name"] == "Luxen"

    def test_a_pledged_duchy_swears_to_the_crown_it_was_pledged_to(self) -> None:
        pledged = self.web(
            self.staff,
            "almanach_set_pledged_liege",
            title_id=self.brittany.pk,
            liege_title_id=self.imperial.pk,
        )
        assert pledged.detail.success, pledged.detail.message
        dukes = OrganizationFactory(name="House Brittany")
        assign_holder(self.brittany, dukes)
        assert FealtyEdge.objects.get(vassal=dukes).liege_id == self.throne.pk

    def test_a_player_is_refused_and_the_picker_lists_only_undefined_houses(self) -> None:
        for key, kwargs in (
            (
                "almanach_charter_fief",
                {"title_id": self.republic.pk, "fief_title_id": self.anjou.pk},
            ),
            ("almanach_record_claim", {"title_id": self.anjou.pk, "house_id": self.throne.pk}),
            ("almanach_set_station", {"title_id": self.anjou.pk, "station": TitleStation.TITULAR}),
            ("almanach_set_pledged_liege", {"title_id": self.anjou.pk, "liege_title_id": None}),
        ):
            refused = self.web(self.player, key, **kwargs)
            assert not refused.detail.success, key
        titular = plant_rung(
            realm=self.realm,
            tier=TitleTier.DUCHY,
            name="Old Anjou",
            parent_title=self.republic,
            station=TitleStation.TITULAR,
        )
        inner = Title.objects.get(seat_domain=self.anjou.seat_domain, tier=TitleTier.COUNTY)
        response = self.api(self.account_of(self.player)).get(
            "/api/character-creation/house-titles/"
        )
        assert response.status_code == 200, response.content
        ids = {t["id"] for t in response.data}
        assert self.anjou.pk in ids
        assert self.republic.pk not in ids
        assert titular.pk not in ids
        assert inner.pk not in ids
