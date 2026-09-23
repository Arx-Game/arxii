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
from world.societies.houses.models import (
    HouseAspectDefinition,
    HouseTemplate,
    NobiliaryParticle,
    SuccessionLaw,
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
            level=AreaLevel.CITY, realm=self.realm, is_capital=True, name="Almanach API Capital"
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
