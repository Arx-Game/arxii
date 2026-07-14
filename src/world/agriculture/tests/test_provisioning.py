"""Tests for army food provisioning at mobilization (#2375)."""

from django.test import TestCase

from world.agriculture.models import FoodStockpile
from world.agriculture.services.production import get_food_config
from world.agriculture.services.provisioning import provision_army


class ProvisionArmyTests(TestCase):
    def setUp(self):
        from world.areas.factories import AreaFactory
        from world.covenants.constants import BattleBinding, CovenantType
        from world.covenants.factories import (
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        self.org = OrganizationFactory()
        self.covenant = CovenantFactory(
            organization=self.org,
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
        )
        self.role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        self.domain1 = Domain.objects.create(
            area=AreaFactory(), name="Domain1", owner_org=self.org, population=100
        )
        self.domain2 = Domain.objects.create(
            area=AreaFactory(), name="Domain2", owner_org=self.org, population=100
        )
        self.stockpile1 = FoodStockpile.objects.create(domain=self.domain1, stored=100)
        self.stockpile2 = FoodStockpile.objects.create(domain=self.domain2, stored=50)

        config = get_food_config()
        config.army_food_per_member = 10
        config.save()

    def _add_engaged_member(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
        )
        from world.covenants.services import set_engaged_membership

        sheet = CharacterSheetFactory()
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=self.covenant,
            covenant_role=self.role,
        )
        set_engaged_membership(membership=membership)
        return membership

    def test_full_supply_ratio_is_one(self):
        """When food is sufficient, ratio is 1.0 and food is deducted proportionally."""
        self._add_engaged_member()
        self._add_engaged_member()
        self._add_engaged_member()

        ratio = provision_army(self.covenant)
        self.covenant.refresh_from_db()

        assert ratio == 1.0
        assert self.covenant.provisioning_ratio == 1.0
        # needed = 3 * 10 = 30, total = 150. domain1: 100/150 * 30 = 20, domain2: 50/150 * 30 = 10
        self.stockpile1.refresh_from_db()
        self.stockpile2.refresh_from_db()
        assert self.stockpile1.stored == 80
        assert self.stockpile2.stored == 40

    def test_shortage_ratio_reflects_shortfall(self):
        """When food is insufficient, ratio reflects shortfall and stockpiles hit 0."""
        self._add_engaged_member()
        self._add_engaged_member()
        self._add_engaged_member()

        self.stockpile1.stored = 5
        self.stockpile1.save()
        self.stockpile2.stored = 5
        self.stockpile2.save()

        ratio = provision_army(self.covenant)
        self.covenant.refresh_from_db()

        # needed = 30, available = 10, ratio = 10/30 = 0.333...
        self.assertAlmostEqual(ratio, 10.0 / 30.0, places=2)
        self.stockpile1.refresh_from_db()
        self.stockpile2.refresh_from_db()
        assert self.stockpile1.stored == 0
        assert self.stockpile2.stored == 0

    def test_no_engaged_members_ratio_is_one(self):
        """No engaged members means no army to feed; ratio is 1.0."""
        ratio = provision_army(self.covenant)
        self.covenant.refresh_from_db()

        assert ratio == 1.0
        self.stockpile1.refresh_from_db()
        self.stockpile2.refresh_from_db()
        assert self.stockpile1.stored == 100  # untouched
        assert self.stockpile2.stored == 50  # untouched

    def test_no_domains_ratio_is_zero(self):
        """Covenant with no domains gets ratio 0.0."""
        from world.covenants.constants import BattleBinding, CovenantType
        from world.covenants.factories import CovenantFactory
        from world.societies.factories import OrganizationFactory

        org = OrganizationFactory()
        covenant = CovenantFactory(
            organization=org,
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
        )
        # No domains created for this org
        self._add_engaged_member_to(covenant)

        ratio = provision_army(covenant)
        covenant.refresh_from_db()

        assert ratio == 0.0
        assert covenant.provisioning_ratio == 0.0

    def test_domain_without_stockpile_treated_as_zero(self):
        """Domain without a FoodStockpile row is treated as 0 stored."""
        from world.areas.factories import AreaFactory
        from world.societies.houses.models import Domain

        # Add a third domain with no stockpile
        Domain.objects.create(
            area=AreaFactory(), name="NoStock", owner_org=self.org, population=100
        )
        self._add_engaged_member()

        ratio = provision_army(self.covenant)
        self.covenant.refresh_from_db()

        # needed = 10, available = 150 (only domain1+domain2 have stockpiles)
        assert ratio == 1.0

    def _add_engaged_member_to(self, covenant):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantRoleFactory,
        )
        from world.covenants.services import set_engaged_membership

        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=covenant,
            covenant_role=role,
        )
        set_engaged_membership(membership=membership)
