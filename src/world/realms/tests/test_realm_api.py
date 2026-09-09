"""Realm page reads (#3725): the hub list, a realm by slug, its organizations and boards,
the roster's realm filter and the starting area's realm slug."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_creation.constants import StartingAreaAccessLevel
from world.character_creation.factories import RealmFactory, StartingAreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.realms.constants import TESTAMENT_THRESHOLD_LINE
from world.realms.models import RealmTestamentSection
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models.choices import RosterType
from world.societies.constants import FameTier
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationTypeFactory,
    SocietyFactory,
)


def _persona_of_realm(name: str, realm, *, roster_type=RosterType.ACTIVE, prestige=0):
    sheet = CharacterSheetFactory(character=CharacterFactory(), origin_realm=realm)
    roster = RosterFactory(roster_type=roster_type)
    if not roster.is_public:
        roster.is_public = True
        roster.save(update_fields=["is_public"])
    entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
    persona = sheet.primary_persona
    persona.name = name
    persona.total_prestige = prestige
    persona.save(update_fields=["name", "total_prestige"])
    return persona, entry


class RealmListAndDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Umbros", formal_name="The Umbral Empire", theme="umbros")
        cls.other = RealmFactory(name="Luxen", theme="luxen")
        RealmTestamentSection.objects.create(
            realm=cls.realm, sort_order=2, body="Second.", motto="Return puissant."
        )
        RealmTestamentSection.objects.create(
            realm=cls.realm, sort_order=1, body="First.", motto="Dare Greatly."
        )
        cls.society = SocietyFactory(name="The Peerage", realm=cls.realm)
        SocietyFactory(name="Elsewhere", realm=cls.other)
        cls.area = StartingAreaFactory(name="Tenebrum", realm=cls.realm)

    def test_list_is_anonymous_and_carries_the_first_motto(self):
        response = APIClient().get("/api/realms/")
        self.assertEqual(response.status_code, 200)
        by_slug = {row["slug"]: row for row in response.json()}
        self.assertEqual(by_slug["umbros"]["formal_name"], "The Umbral Empire")
        self.assertEqual(by_slug["umbros"]["first_motto"], "Dare Greatly.")
        self.assertEqual(by_slug["luxen"]["first_motto"], "")
        self.assertEqual(by_slug["luxen"]["theme"], "luxen")

    def test_retrieve_by_slug_gives_sections_in_order_and_own_societies(self):
        response = APIClient().get("/api/realms/umbros/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["threshold_line"], TESTAMENT_THRESHOLD_LINE)
        self.assertEqual(
            [s["motto"] for s in data["sections"]], ["Dare Greatly.", "Return puissant."]
        )
        self.assertEqual([s["name"] for s in data["societies"]], ["The Peerage"])
        self.assertEqual(set(data["societies"][0]), {"id", "name", "description", "enforcer_name"})
        self.assertEqual(data["starting_area"]["name"], "Tenebrum")
        self.assertIsNone(data["starting_area"]["crest_image"])

    def test_gated_starting_area_is_null_for_a_visitor_and_the_realm_still_lists(self):
        gated = RealmFactory(name="Ariwn")
        StartingAreaFactory(
            name="Kys G'Sheer", realm=gated, access_level=StartingAreaAccessLevel.TRUST_REQUIRED
        )
        client = APIClient()
        self.assertIn("ariwn", [row["slug"] for row in client.get("/api/realms/").json()])
        detail = client.get("/api/realms/ariwn/").json()
        self.assertIsNone(detail["starting_area"])

    def test_unknown_slug_is_404(self):
        self.assertEqual(APIClient().get("/api/realms/nowhere/").status_code, 404)

    def test_starting_area_read_carries_the_realm_slug(self):
        response = APIClient().get("/api/character-creation/starting-areas/")
        self.assertEqual(response.status_code, 200)
        rows = {row["name"]: row for row in response.json()}
        self.assertEqual(rows["Tenebrum"]["realm_slug"], "umbros")
        self.assertEqual(rows["Tenebrum"]["realm_name"], "Umbros")


class RealmOrganizationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Umbros")
        society = SocietyFactory(name="The Peerage", realm=cls.realm)
        other_society = SocietyFactory(name="Elsewhere", realm=RealmFactory(name="Luxen"))
        noble = OrganizationTypeFactory(name="noble")
        cls.covert_type = OrganizationTypeFactory(name="cabal", is_covert=True)
        cls.house = OrganizationFactory(
            name="House Veyle", society=society, org_type=noble, words="Dare.", colors="black"
        )
        OrganizationFactory(name="House Elsewhere", society=other_society, org_type=noble)
        cls.cabal = OrganizationFactory(
            name="The Masquers", society=society, org_type=cls.covert_type
        )

    def test_visitor_sees_shop_window_fields_and_no_covert_row(self):
        response = APIClient().get("/api/realms/umbros/organizations/")
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual([r["name"] for r in rows], ["House Veyle"])
        self.assertEqual(
            set(rows[0]),
            {
                "id",
                "name",
                "description",
                "words",
                "colors",
                "sigil_description",
                "org_type_name",
                "society_name",
            },
        )

    def test_member_of_the_covert_row_sees_it_and_a_non_member_does_not(self):
        persona, entry = _persona_of_realm("Isolde", self.realm)
        account = AccountFactory()
        RosterTenureFactory(roster_entry=entry, player_data=PlayerDataFactory(account=account))
        OrganizationMembershipFactory(persona=persona, organization=self.cabal)
        member = APIClient()
        member.force_login(account)
        self.assertEqual(
            [r["name"] for r in member.get("/api/realms/umbros/organizations/").json()],
            ["The Masquers", "House Veyle"],
        )
        stranger = APIClient()
        stranger.force_login(AccountFactory())
        self.assertEqual(
            [r["name"] for r in stranger.get("/api/realms/umbros/organizations/").json()],
            ["House Veyle"],
        )


class RealmNotablesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Umbros")
        cls.elsewhere = RealmFactory(name="Luxen")

    def test_boards_rank_active_personas_of_the_realm_by_renown_without_numbers(self):
        _persona_of_realm("Low", self.realm, prestige=100)
        _persona_of_realm("High", self.realm, prestige=200)
        famous, _ = _persona_of_realm("Famous", self.realm, prestige=150)
        famous.fame_tier = FameTier.CELEBRITY
        famous.save(update_fields=["fame_tier"])
        _persona_of_realm("Lapsed", self.realm, roster_type=RosterType.INACTIVE, prestige=900)
        _persona_of_realm("Foreign", self.elsewhere, prestige=900)
        response = APIClient().get("/api/realms/umbros/notables/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([r["persona_name"] for r in data["renown"]], ["Famous", "High", "Low"])
        self.assertEqual(set(data["renown"][0]), {"persona_name", "band_label"})
        self.assertIsInstance(data["legend"], list)

    def test_empty_realm_has_empty_boards(self):
        from world.societies.ranking_services import get_realm_legend_top_n, get_realm_renown_top_n

        self.assertEqual(get_realm_renown_top_n(self.realm), [])
        self.assertEqual(get_realm_legend_top_n(self.realm), [])
        data = APIClient().get("/api/realms/umbros/notables/").json()
        self.assertEqual(data, {"renown": [], "legend": []})


class RosterRealmFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Umbros")
        cls.elsewhere = RealmFactory(name="Luxen")

    def test_realm_filter_matches_the_sheet_origin_and_unknown_slug_matches_nothing(self):
        _, entry = _persona_of_realm("Isolde", self.realm)
        _persona_of_realm("Foreign", self.elsewhere)
        nowhere = CharacterSheetFactory(character=CharacterFactory(), origin_realm=None)
        RosterEntryFactory(
            character_sheet=nowhere, roster=RosterFactory(roster_type=RosterType.ACTIVE)
        )
        client = APIClient()
        raw = client.get("/api/roster/entries/?realm=umbros")
        self.assertEqual(raw.status_code, 200, raw.content)
        ids = [r["id"] for r in raw.json()["results"]]
        self.assertEqual(ids, [entry.id])
        self.assertEqual(client.get("/api/roster/entries/?realm=nowhere").json()["count"], 0)
