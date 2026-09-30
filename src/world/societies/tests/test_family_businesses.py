"""Family businesses on another's land (#4060 slice 4): owner_org on a holding."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.currency.constants import IncomeStreamKind
from world.currency.models import OrgIncomeStream
from world.currency.services import accrue_income_stream
from world.societies.constants import LevyKind
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import HoldingSiteKind
from world.societies.houses.factories import HoldingKindFactory
from world.societies.houses.services import add_holding, create_domain
from world.societies.levies import set_levy


class FamilyBusinessTests(TestCase):
    def setUp(self):
        self.city = AreaFactory(level=AreaLevel.BARONY)
        self.mayor = OrganizationFactory(name="Office of the Lord Mayor")
        self.family = OrganizationFactory(name="Cisternwrights")
        self.domain = create_domain(area=self.city, name="Luxen", owner_org=self.mayor)
        self.kind = HoldingKindFactory(
            name="Tavern", site_kind=HoldingSiteKind.BUILDING, base_gross=1000, units_required=0
        )

    def test_a_family_may_own_a_business_on_someone_elses_domain(self):
        holding = add_holding(
            domain=self.domain, kind=self.kind, owner_org=self.family, unsited=True, standing=80
        )

        self.assertEqual(holding.owner_org, self.family)
        self.assertEqual(holding.owner, self.family)
        self.assertEqual(holding.income_stream.organization, self.family)
        self.assertEqual(holding.standing, 80)

    def test_the_domains_owner_taxes_a_family_business_on_its_land(self):
        room = RoomProfileFactory(area=self.city, is_outdoor=True)
        yard = HoldingKindFactory(name="Yard", site_kind=HoldingSiteKind.LAND, base_gross=1000)
        holding = add_holding(
            domain=self.domain, kind=yard, owner_org=self.family, room_profile=room
        )
        set_levy(self.city, LevyKind.TAX, 10)

        accrue_income_stream(holding.income_stream)

        holding.income_stream.refresh_from_db()
        self.assertEqual(holding.income_stream.uncollected_pool, 900)
        mayor_levy = OrgIncomeStream.objects.get(
            organization=self.mayor, kind=IncomeStreamKind.LEVY
        )
        self.assertEqual(mayor_levy.uncollected_pool, 100)

    def test_a_holding_with_no_owner_override_belongs_to_the_domains_owner(self):
        holding = add_holding(domain=self.domain, kind=self.kind, unsited=True)
        self.assertIsNone(holding.owner_org)
        self.assertEqual(holding.owner, self.mayor)
