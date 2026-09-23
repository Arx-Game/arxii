"""Tests for the Almanach de Catenys API (#3983 Task 5): the staff-only
realm ladder, house document, and land-shape reads."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import RealmFactory
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import plant_rung, publish_house
from world.societies.houses.constants import SuccessionDerivation, TitleTier
from world.societies.houses.models import SuccessionLaw


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

    def test_ladder_founder_cut_is_also_staff_gated(self) -> None:
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

    def test_players_are_refused(self) -> None:
        client = APIClient()
        client.force_authenticate(self.player)
        assert client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/").status_code == 403
        assert client.get(f"/api/almanach/houses/{self.crown.pk}/document/").status_code == 403
        assert client.get("/api/almanach/land-shapes/").status_code == 403

    def test_anonymous_requests_are_refused(self) -> None:
        client = APIClient()
        assert client.get(f"/api/almanach/realms/{self.realm.pk}/ladder/").status_code in (
            401,
            403,
        )
