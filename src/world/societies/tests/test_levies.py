"""Levies (#4060 slice 3): every controller above a business takes its cut."""

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
from world.societies.levies import ensure_levy_streams, set_levy
from world.societies.turf_services import apply_turf_push


class LevyTests(TestCase):
    def setUp(self):
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=self.ward)
        self.corner = RoomProfileFactory(area=self.neighborhood, is_outdoor=True)
        self.mayor = OrganizationFactory(name="Office of the Lord Mayor")
        self.baron = OrganizationFactory(name="House Orisant")
        self.gang = OrganizationFactory(name="Ashfingers")
        create_domain(area=self.city, name="Luxen", owner_org=self.mayor)
        self.ward_domain = create_domain(area=self.ward, name="Orisant Ward", owner_org=self.baron)
        apply_turf_push(self.gang, self.neighborhood, 50)
        kind = HoldingKindFactory(
            name="Tavern Yard", site_kind=HoldingSiteKind.LAND, base_gross=1000
        )
        self.tavern = add_holding(domain=self.ward_domain, kind=kind, room_profile=self.corner)

    def _pool(self, org, kind):
        return sum(
            OrgIncomeStream.objects.filter(organization=org, kind=kind).values_list(
                "uncollected_pool", flat=True
            )
        )

    def test_a_business_pays_every_controller_above_it_and_never_either_or(self):
        set_levy(self.city, LevyKind.TAX, 10)
        set_levy(self.neighborhood, LevyKind.PROTECTION, 20)

        accrue_income_stream(self.tavern.income_stream)

        self.tavern.income_stream.refresh_from_db()
        self.assertEqual(self.tavern.income_stream.uncollected_pool, 700)
        self.assertEqual(self._pool(self.mayor, IncomeStreamKind.LEVY), 100)
        self.assertEqual(self._pool(self.gang, IncomeStreamKind.LEVY), 200)

    def test_a_controller_does_not_levy_its_own_holdings(self):
        set_levy(self.ward, LevyKind.TAX, 50)

        accrue_income_stream(self.tavern.income_stream)

        self.tavern.income_stream.refresh_from_db()
        self.assertEqual(self.tavern.income_stream.uncollected_pool, 1000)
        self.assertEqual(self._pool(self.baron, IncomeStreamKind.LEVY), 0)

    def test_contested_ground_collects_nothing(self):
        set_levy(self.ward, LevyKind.PROTECTION, 30)  # no turf on the ward: nobody holds it

        accrue_income_stream(self.tavern.income_stream)

        self.tavern.income_stream.refresh_from_db()
        self.assertEqual(self.tavern.income_stream.uncollected_pool, 1000)
        self.assertFalse(OrgIncomeStream.objects.filter(kind=IncomeStreamKind.LEVY).exists())

    def test_the_take_follows_a_flip(self):
        set_levy(self.neighborhood, LevyKind.PROTECTION, 20)
        accrue_income_stream(self.tavern.income_stream)
        rival = OrganizationFactory(name="Rival Gang")

        apply_turf_push(rival, self.neighborhood, 80)
        accrue_income_stream(self.tavern.income_stream)

        # The uncollected pool moves with the ground, as kick-up does.
        self.assertEqual(self._pool(rival, IncomeStreamKind.LEVY), 400)
        self.assertEqual(self._pool(self.gang, IncomeStreamKind.LEVY), 0)

    def test_levies_never_take_more_than_the_gross(self):
        set_levy(self.city, LevyKind.TAX, 60)
        set_levy(self.neighborhood, LevyKind.PROTECTION, 60)

        accrue_income_stream(self.tavern.income_stream)

        self.tavern.income_stream.refresh_from_db()
        self.assertEqual(self.tavern.income_stream.uncollected_pool, 0)
        self.assertEqual(self._pool(self.mayor, IncomeStreamKind.LEVY), 500)
        self.assertEqual(self._pool(self.gang, IncomeStreamKind.LEVY), 500)

    def test_a_zero_rate_switches_the_levy_off_and_the_weekly_phase_resets_the_display(self):
        levy = set_levy(self.city, LevyKind.TAX, 10)
        accrue_income_stream(self.tavern.income_stream)
        levy.refresh_from_db()
        self.assertEqual(levy.income_stream.gross_amount, 100)

        ensure_levy_streams()
        levy.income_stream.refresh_from_db()
        self.assertEqual(levy.income_stream.gross_amount, 0)

        set_levy(self.city, LevyKind.TAX, 0)
        accrue_income_stream(self.tavern.income_stream)
        self.assertEqual(self._pool(self.mayor, IncomeStreamKind.LEVY), 100)

    def test_a_levy_stream_accrues_nothing_on_its_own(self):
        levy = set_levy(self.city, LevyKind.TAX, 10)
        ensure_levy_streams()
        levy.refresh_from_db()

        accrue_income_stream(levy.income_stream)

        levy.income_stream.refresh_from_db()
        self.assertEqual(levy.income_stream.uncollected_pool, 0)
