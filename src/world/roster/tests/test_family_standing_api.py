"""The CG family list shows how an established family is doing (#4060 slice 4)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.factories import HoldingKindFactory
from world.societies.houses.services import add_holding, create_domain


class FamilyStandingApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user("standing_viewer", "s@example.com", "pw-1234")
        cls.city = AreaFactory(level=AreaLevel.CITY)
        cls.mayor = OrganizationFactory(name="Office of the Lord Mayor")
        cls.home = create_domain(area=cls.city, name="Luxen", owner_org=cls.mayor)

        cls.landed = FamilyFactory(name="Orisant", is_playable=True)
        landed_org = OrganizationFactory(name="House Orisant", family=cls.landed)
        seat = create_domain(
            area=AreaFactory(level=AreaLevel.BARONY), name="Orisant Vale", owner_org=landed_org
        )
        seat.prosperity = 70
        seat.save(update_fields=["prosperity"])

        cls.trading = FamilyFactory(name="Cisternwrights", is_playable=True)
        trading_org = OrganizationFactory(name="Cisternwrights", family=cls.trading)
        kind = HoldingKindFactory(name="Tavern", base_gross=1000)
        add_holding(domain=cls.home, kind=kind, owner_org=trading_org, unsited=True, standing=80)
        add_holding(domain=cls.home, kind=kind, owner_org=trading_org, unsited=True, standing=40)

        cls.landless = FamilyFactory(name="Nobodies", is_playable=True)

    def _rows(self):
        client = APIClient()
        client.force_authenticate(self.account)
        res = client.get("/api/character-creation/families/")
        assert res.status_code == 200, res.content
        return {row["name"]: row for row in res.json()}

    def test_a_landed_family_reads_its_seats_prosperity(self):
        assert self._rows()["Orisant"]["standing"] == 70

    def test_a_trading_family_reads_the_mean_standing_of_its_businesses(self):
        assert self._rows()["Cisternwrights"]["standing"] == 60

    def test_a_family_with_nothing_has_no_standing(self):
        assert self._rows()["Nobodies"]["standing"] is None
