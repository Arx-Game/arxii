"""Tests for the weekly domain consumption tick."""

from django.test import TestCase

from world.agriculture.services import domain_consumption_tick


class DomainConsumptionTickTests(TestCase):
    def test_no_domains_no_op(self):
        result = domain_consumption_tick()
        self.assertEqual(result["domains_processed"], 0)

    def test_sufficient_food_no_penalty(self):
        from world.agriculture.models import FoodStockpile
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        domain = Domain.objects.create(
            area=AreaFactory(), name="Test", owner_org=org, population=100
        )
        FoodStockpile.objects.create(domain=domain, stored=200)

        result = domain_consumption_tick()
        self.assertEqual(result["shortages"], 0)

        stockpile = FoodStockpile.objects.get(domain=domain)
        self.assertEqual(stockpile.stored, 100)  # 200 - 100

    def test_shortage_raises_unrest_lowers_prosperity(self):
        from world.agriculture.models import FoodStockpile
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        domain = Domain.objects.create(
            area=AreaFactory(), name="Test2", owner_org=org, population=100
        )
        FoodStockpile.objects.create(domain=domain, stored=50)

        result = domain_consumption_tick()
        self.assertEqual(result["shortages"], 1)

        domain.refresh_from_db()
        self.assertEqual(domain.unrest, 15)  # 10 default + 5 penalty
        self.assertEqual(domain.prosperity, 45)  # 50 default - 5 penalty

    def test_well_fed_week_recovers_prosperity_and_relaxes_unrest(self):
        # #2238 — a well-fed domain isn't permanently punished for one bad week.
        from world.agriculture.models import FoodStockpile
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        domain = Domain.objects.create(
            area=AreaFactory(), name="Rec", owner_org=org, population=100, prosperity=40, unrest=20
        )
        FoodStockpile.objects.create(domain=domain, stored=200)

        domain_consumption_tick()

        domain.refresh_from_db()
        self.assertEqual(domain.unrest, 18)  # 20 - 2 relief
        self.assertEqual(domain.prosperity, 42)  # 40 + 2 gain, toward equilibrium 50

    def test_recovery_never_decays_prosperity_above_equilibrium(self):
        # Improvements that pushed prosperity above the baseline are left untouched.
        from world.agriculture.models import FoodStockpile
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        domain = Domain.objects.create(
            area=AreaFactory(), name="Rec2", owner_org=org, population=100, prosperity=60, unrest=20
        )
        FoodStockpile.objects.create(domain=domain, stored=200)

        domain_consumption_tick()

        domain.refresh_from_db()
        self.assertEqual(domain.prosperity, 60)  # above equilibrium 50 → untouched
        self.assertEqual(domain.unrest, 18)  # unrest still relaxes

    def test_no_stockpile_treated_as_shortage(self):
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        domain = Domain.objects.create(
            area=AreaFactory(), name="Test3", owner_org=org, population=100
        )

        result = domain_consumption_tick()
        self.assertEqual(result["shortages"], 1)

        domain.refresh_from_db()
        self.assertEqual(domain.unrest, 15)
        self.assertEqual(domain.prosperity, 45)
