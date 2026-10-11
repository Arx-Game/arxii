"""Tests for the Almanach de Catenys API (#3983 Task 5, Plan B Task 3): the
realm/founder reads (open to any authenticated account), plus the
staff-only ladder cut, house list/document, and house-authoring surface."""

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.roster.constants import NOBLE_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory
from world.roster.services.kinship import OMNISCIENT
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import plant_rung, publish_house
from world.societies.houses.almanach_reads import document_for_house
from world.societies.houses.constants import SuccessionDerivation, TitleTier
from world.societies.houses.factories import OrganizationObservanceFactory
from world.societies.houses.models import (
    HouseAspectDefinition,
    HouseTemplate,
    NobiliaryParticle,
    SuccessionLaw,
    Title,
)


class AlmanachApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="almanach_staff", is_staff=True)
        cls.player = AccountFactory(username="almanach_player", is_staff=False)
        cls.realm = RealmFactory(name="Inferna")
        cls.law = SuccessionLaw.objects.create(
            name="Almanach API Test Law",
            derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK,
        )
        # A family (not just an org): the houses viewset queryset is
        # `family__isnull=False` (#3983 Task 5 ruling 2) — a real house
        # always has one, unlike the plain-org fixture in the task brief.
        cls.crown = OrganizationFactory(
            name="Piropa",
            family=FamilyFactory(name="House Piropa", origin_realm=cls.realm),
            default_succession_law=cls.law,
        )
        cls.kingdom = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=cls.crown
        )
        publish_house(cls.crown)

    def test_staff_reads_the_ladder_and_the_document(self) -> None:
        client = APIClient()
        client.force_authenticate(self.staff)
        res = client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/")
        assert res.status_code == 200
        assert res.data["unclaimed_by_tier"]["duchy"] == 0
        assert any(r["is_seat_of"] == "Piropa" for r in res.data["rows"])
        res = client.get(f"/api/almanach/houses/{self.crown.pk}/document/")
        assert res.status_code == 200
        assert res.data["lands"]["count"] == 1
        # #3983 Task 5, ruling 1: SuccessionLaw.codex_entry is new on this
        # task; the document must carry the key, unset by default.
        law_payload = res.data["house"]["default_succession_law"]
        assert law_payload["name"] == self.law.name
        assert law_payload["codex_entry_id"] is None

    def test_a_title_with_no_seat_reads_as_its_own_chain_top(self) -> None:
        """#4237: ``Title.seat_domain`` is nullable, and goes null when the seat's
        domain is deleted. A seatless title shares its seat with nothing, so it is
        its own chain top, as ``chain_top_id`` already said. Read as a chain member
        instead, its row looked up the chain top of seat ``None`` and raised, and
        the realm list, which builds every realm's ladder, answered 500."""
        realm = RealmFactory(name="Seatless Realm")
        unclaimed = Title.objects.create(
            realm=realm, tier=TitleTier.BARONY, name="Barony of Nowhere", is_claimable=True
        )
        house = OrganizationFactory(
            name="Landless", family=FamilyFactory(name="House Landless", origin_realm=realm)
        )
        held = Title.objects.create(realm=realm, tier=TitleTier.BARONY, name="Lost", house=house)
        client = APIClient()
        client.force_authenticate(self.staff)

        assert client.get("/api/almanach/realms/").status_code == 200
        res = client.get(f"/api/almanach/realms/{realm.pk}/ladder/")
        assert res.status_code == 200
        rows = {row["title_id"]: row for row in res.data["rows"]}
        for title in (unclaimed, held):
            assert rows[title.pk]["chain_top_id"] == title.pk
            assert rows[title.pk]["sworn_to"] == ""
            assert rows[title.pk]["comes_with"] == ""
        # A held seatless barony is nobody's seat; an unclaimed one counts at its tier.
        assert rows[held.pk]["is_seat_of"] == ""
        assert res.data["unclaimed_by_tier"]["barony"] == 1
        assert client.get(f"/api/almanach/houses/{house.pk}/document/").status_code == 200

    def test_document_carries_the_houses_days_of_remembrance(self) -> None:
        """#4206: the house section lists its observances in calendar order,
        each spelled with the game's one IC date formatter."""
        OrganizationObservanceFactory(
            organization=self.crown, ic_month=10, ic_day=18, name="Founding Night", lore="Fire."
        )
        OrganizationObservanceFactory(organization=self.crown, ic_month=1, ic_day=2, name="Vigil")
        client = APIClient()
        client.force_authenticate(self.staff)
        res = client.get(f"/api/almanach/houses/{self.crown.pk}/document/")
        assert res.status_code == 200
        assert res.data["house"]["observances"] == [
            {"ic_month": 1, "ic_day": 2, "name": "Vigil", "lore": "", "when": "Dreaming 2 (1/2)"},
            {
                "ic_month": 10,
                "ic_day": 18,
                "name": "Founding Night",
                "lore": "Fire.",
                "when": "Masquing 18 (10/18)",
            },
        ]

    def test_staff_document_read_passes_the_omniscient_viewer(self) -> None:
        # Review finding (#3983 Task 5): the document action must resolve the
        # kinship-read viewer the same way roster's own views do — staff ->
        # OMNISCIENT — not a CharacterSheet. Wrap the real function so the
        # request still round-trips normally; just record the call's viewer.
        client = APIClient()
        client.force_authenticate(self.staff)
        with patch(
            "world.societies.houses.almanach_views.document_for_house",
            wraps=document_for_house,
        ) as mock_document_for_house:
            res = client.get(f"/api/almanach/houses/{self.crown.pk}/document/")
        assert res.status_code == 200
        assert mock_document_for_house.call_args.kwargs["viewer"] is OMNISCIENT

    def test_staff_can_still_reach_the_founder_ladder_cut(self) -> None:
        """The ``?for=founder`` cut opened to every authenticated account
        (#3983 Plan B Task 3) stays reachable by staff too."""
        client = APIClient()
        client.force_authenticate(self.staff)
        res = client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/?for=founder")
        assert res.status_code == 200

    def test_land_shapes_list_is_staff_reachable(self) -> None:
        client = APIClient()
        client.force_authenticate(self.staff)
        res = client.get("/api/almanach/land-shapes/")
        assert res.status_code == 200

    def test_houses_list_filters_by_realm(self) -> None:
        client = APIClient()
        client.force_authenticate(self.staff)
        res = client.get(f"/api/almanach/houses/?realm={self.realm.pk}")
        assert res.status_code == 200
        assert any(h["id"] == self.crown.pk for h in res.data["results"])
        other_realm = RealmFactory(name="Umbros")
        res = client.get(f"/api/almanach/houses/?realm={other_realm.pk}")
        assert res.status_code == 200
        assert all(h["id"] != self.crown.pk for h in res.data["results"])

    def test_houses_list_carries_family_id(self) -> None:
        """#3983 Task 10 fold-in: the house summary needs the raw
        ``Organization.family_id`` for AddKinDialog's "born into" pick
        (a ``Family`` pk, never this row's own ``Organization`` id)."""
        client = APIClient()
        client.force_authenticate(self.staff)
        res = client.get(f"/api/almanach/houses/{self.crown.pk}/")
        assert res.status_code == 200
        assert res.data["family_id"] == self.crown.family_id

    def test_players_are_refused_the_staff_cut_and_the_house_document(self) -> None:
        """#3983 Plan B Task 3: only the ``?for=staff`` ladder cut and the
        houses viewset (list/document) stay admin-only for a non-staff
        account — see ``test_non_staff_reaches_the_founder_reads`` for the
        surfaces opened to every authenticated account."""
        client = APIClient()
        client.force_authenticate(self.player)
        assert client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/").status_code == 403
        assert (
            client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/?for=staff").status_code == 403
        )
        assert client.get(f"/api/almanach/houses/{self.crown.pk}/").status_code == 403
        assert client.get(f"/api/almanach/houses/{self.crown.pk}/document/").status_code == 403

    def test_non_staff_reaches_the_founder_reads(self) -> None:
        """#3983 Plan B Task 3: the realm picker, the founder ladder cut, the
        land-shape catalog, and the realm charter are open to any
        authenticated account so a founder can read them mid-draft."""
        client = APIClient()
        client.force_authenticate(self.player)
        assert client.get("/api/almanach/realms/").status_code == 200
        res = client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/?for=founder")
        assert res.status_code == 200
        assert client.get("/api/almanach/land-shapes/").status_code == 200
        assert client.get(f"/api/almanach/realms/{self.realm.pk}/charter/").status_code == 200

    def test_anonymous_requests_are_refused_the_founder_reads_too(self) -> None:
        client = APIClient()
        assert client.get("/api/almanach/realms/").status_code in (401, 403)
        assert client.get("/api/almanach/land-shapes/").status_code in (401, 403)
        assert client.get(f"/api/almanach/realms/{self.realm.pk}/charter/").status_code in (
            401,
            403,
        )

    def test_charter_reads_the_realms_defaults(self) -> None:
        """#3983 Plan B Task 3: the default template's succession law, the
        blank-floor Noble particle, the default template's first aspect
        prompt, and the realm's capital name."""
        template = HouseTemplate.objects.create(
            name="Almanach API Charter Template",
            realm=self.realm,
            kind=FamilyKindFactory(name=NOBLE_KIND_NAME),
            society=self.crown.society,
            org_type=self.crown.org_type,
            liege=self.crown,
            default_succession_law=self.law,
        )
        quiddity = HouseAspectDefinition.objects.create(
            name="Almanach API Quiddity", prompt="Which virtue rules the house?"
        )
        template.aspect_definitions.add(quiddity)
        NobiliaryParticle.objects.create(
            realm=self.realm, kind=template.kind, particle="del", taken_in_particle="von"
        )
        AreaFactory(
            level=AreaLevel.BARONY, realm=self.realm, is_capital=True, name="Almanach API Capital"
        )

        client = APIClient()
        client.force_authenticate(self.player)
        res = client.get(f"/api/almanach/realms/{self.realm.pk}/charter/")
        assert res.status_code == 200
        assert res.data["succession_law"]["name"] == self.law.name
        assert res.data["particle"] == {"born": "del", "taken_in": "von"}
        assert res.data["quiddity_prompt"] == "Which virtue rules the house?"
        assert res.data["capital_name"] == "Almanach API Capital"

    def test_charter_with_no_authored_rows_is_all_blank(self) -> None:
        empty_realm = RealmFactory(name="Charterless")
        client = APIClient()
        client.force_authenticate(self.player)
        res = client.get(f"/api/almanach/realms/{empty_realm.pk}/charter/")
        assert res.status_code == 200
        assert res.data["succession_law"] is None
        assert res.data["particle"] == {"born": "", "taken_in": ""}
        assert res.data["quiddity_prompt"] == ""
        assert res.data["capital_name"] == ""

    def test_anonymous_requests_are_refused(self) -> None:
        client = APIClient()
        assert client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/").status_code in (
            401,
            403,
        )


class AlmanachPagesApiTests(TestCase):
    """#4239: the people, titles and families documents, the front rolls and
    search. Every route is staff-only."""

    @classmethod
    def setUpTestData(cls):
        from world.roster.constants import DefinitionTier
        from world.roster.factories import KinspersonFactory
        from world.societies.houses.almanach import create_family, create_kin
        from world.societies.houses.constants import HoldingChoice
        from world.societies.houses.factories import HouseTemplateFactory

        cls.staff = AccountFactory(username="pages_staff", is_staff=True)
        cls.player = AccountFactory(username="pages_player", is_staff=False)
        cls.realm = RealmFactory(name="Umbros")
        noble = FamilyKindFactory(name=NOBLE_KIND_NAME)
        cls.commoners = FamilyKindFactory(name="Commoner")
        crown = OrganizationFactory(
            name="The Umbral Crown", family=FamilyFactory(name="House Crown", kind=noble)
        )
        throne = plant_rung(realm=cls.realm, tier=TitleTier.KINGDOM, name="Umbros", held_by=crown)
        cls.kathryn = KinspersonFactory(
            name="Kathryn mar Katta", definition_tier=DefinitionTier.STANDING
        )
        made = create_family(
            kind=noble,
            name="Katta",
            realm=cls.realm,
            template=HouseTemplateFactory(realm=cls.realm, kind=noble),
            holding=HoldingChoice.CREATE,
            title_tier=TitleTier.DUCHY,
            title_name="Duchy of Katta",
            parent_title=throne,
            holder=cls.kathryn,
        )
        cls.house = made.organization
        cls.duchy = made.title
        cls.teale = create_family(kind=cls.commoners, name="Teale", realm=cls.realm).family
        create_kin(family=cls.teale, name="Mara Teale")

    def _staff(self) -> APIClient:
        client = APIClient()
        client.force_authenticate(self.staff)
        return client

    def test_every_route_is_staff_only(self) -> None:
        client = APIClient()
        client.force_authenticate(self.player)
        for url in (
            "/api/almanach/front/",
            "/api/almanach/search/?q=Katt",
            f"/api/almanach/people/{self.kathryn.pk}/document/",
            f"/api/almanach/titles/{self.duchy.pk}/document/",
            f"/api/almanach/families/{self.teale.pk}/document/",
            "/api/almanach/people/",
        ):
            assert client.get(url).status_code == 403, url
        client = APIClient()
        assert client.get("/api/almanach/front/").status_code in (401, 403)

    def test_front_and_search(self) -> None:
        client = self._staff()
        res = client.get("/api/almanach/front/")
        assert res.status_code == 200
        # The organization factory seeds a realm through its society, so more
        # than Umbros is listed; Umbros is the one with rungs.
        umbros = next(r for r in res.data["noble"] if r["name"] == "Umbros")
        assert umbros["titles"] >= 2
        assert [r["name"] for r in res.data["commoner"]] == ["Teale"]
        res = client.get("/api/almanach/front/?q=tea")
        assert [r["name"] for r in res.data["commoner"]] == ["Teale"]
        assert client.get("/api/almanach/search/?q=K").data == []
        hits = client.get("/api/almanach/search/?q=Katt").data
        assert {h["kind"] for h in hits} == {"person", "family", "organization", "title"}

    def test_person_title_and_family_documents(self) -> None:
        client = self._staff()
        res = client.get(f"/api/almanach/people/{self.kathryn.pk}/document/")
        assert res.status_code == 200
        assert res.data["person"]["tier_display"]["label"] == "Standing NPC"
        assert res.data["titles"][0]["name"] == "Duchy of Katta"
        assert res.data["house"]["name"] == "House Katta"
        res = client.get(f"/api/almanach/titles/{self.duchy.pk}/document/")
        assert res.status_code == 200
        assert res.data["title"]["holder"] == "Kathryn mar Katta"
        assert res.data["books"]["treasury"] == 0
        assert res.data["vassals"] == []
        res = client.get(f"/api/almanach/families/{self.teale.pk}/document/")
        assert res.status_code == 200
        assert res.data["organization_id"] is None
        assert [n["name"] for n in res.data["tree"]["nodes"]] == ["Mara Teale"]
        assert res.data["tree"]["nodes"][0]["is_missing"] is False
        assert res.data["tree"]["nodes"][0]["obituary"] == ""
        res = client.get(f"/api/almanach/houses/{self.house.pk}/document/")
        assert res.status_code == 200
        assert res.data["turf"] is None
        assert res.data["books"]["streams"] >= 0
        assert "openings" in res.data

    def test_lists_filter(self) -> None:
        client = self._staff()
        res = client.get(f"/api/almanach/people/?family={self.teale.pk}")
        assert [r["name"] for r in res.data["results"]] == ["Mara Teale"]
        res = client.get(f"/api/almanach/titles/?realm={self.realm.pk}&tier={TitleTier.DUCHY}")
        # The kingdom's own chain carries an unnamed duchy-tier rung too.
        assert "Duchy of Katta" in [r["name"] for r in res.data["results"]]
        res = client.get(f"/api/almanach/families/?kind={self.commoners.pk}")
        assert [r["name"] for r in res.data["results"]] == ["Teale"]

    def test_catalog_lists(self) -> None:
        from world.roster.factories import UnionKindFactory
        from world.societies.houses.factories import HouseTemplateFactory

        UnionKindFactory(name="Marriage", realm=self.realm)
        HouseTemplateFactory(realm=self.realm, kind=self.commoners, name="Umbral commoners")
        client = self._staff()
        res = client.get("/api/almanach/kinds/")
        assert res.status_code == 200
        assert "Commoner" in [r["name"] for r in res.data["results"]]
        res = client.get(f"/api/almanach/templates/?realm={self.realm.pk}&kind={self.commoners.pk}")
        assert [r["name"] for r in res.data["results"]] == ["Umbral commoners"]
        res = client.get(f"/api/almanach/union-kinds/?realm={self.realm.pk}")
        assert [r["name"] for r in res.data["results"]] == ["Marriage"]
        client = APIClient()
        client.force_authenticate(self.player)
        assert client.get("/api/almanach/kinds/").status_code == 403
