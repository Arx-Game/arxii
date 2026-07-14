from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.services import rise_battle_covenant_via_session, stand_down_battle_covenant
from world.magic.constants import ParticipantState, ReferenceKind
from world.magic.factories import RitualSessionFactory, RitualSessionParticipantFactory
from world.magic.models.sessions import RitualSessionReference


class BattleRiseServiceTests(TestCase):
    def setUp(self):
        self.cov = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=True,
        )
        self.role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        self.sheet = CharacterSheetFactory()
        self.membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )

    def _rise_session(self):
        session = RitualSessionFactory()
        RitualSessionReference.objects.create(
            session=session, kind=ReferenceKind.COVENANT, ref_covenant=self.cov
        )
        RitualSessionParticipantFactory(
            session=session, character_sheet=self.sheet, state=ParticipantState.ACCEPTED
        )
        return session

    def test_rise_flips_dormant_and_engages_participants(self):
        result = rise_battle_covenant_via_session(session=self._rise_session())
        self.cov.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertFalse(self.cov.is_dormant)
        self.assertTrue(self.membership.engaged)
        self.assertEqual(result, self.cov)

    def test_stand_down_makes_dormant_and_clears_engagement(self):
        self.cov.is_dormant = False
        self.cov.save(update_fields=["is_dormant"])
        from world.covenants.services import set_engaged_membership

        set_engaged_membership(membership=self.membership)
        stand_down_battle_covenant(covenant=self.cov)
        self.cov.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertTrue(self.cov.is_dormant)
        self.assertFalse(self.membership.engaged)

    def test_rise_sets_provisioning_ratio(self):
        """Rising a battle covenant calls provision_army and sets provisioning_ratio."""
        from world.agriculture.models import FoodStockpile
        from world.areas.factories import AreaFactory
        from world.societies.houses.models import Domain

        # Give the covenant's org a domain with food so provisioning is > 0
        domain = Domain.objects.create(
            area=AreaFactory(), name="ProvDomain", owner_org=self.cov.organization, population=100
        )
        FoodStockpile.objects.create(domain=domain, stored=100)

        result = rise_battle_covenant_via_session(session=self._rise_session())
        result.refresh_from_db()

        assert result.provisioning_ratio is not None

    def test_stand_down_clears_provisioning_ratio(self):
        """Standing down clears provisioning_ratio back to None."""
        from world.agriculture.models import FoodStockpile
        from world.areas.factories import AreaFactory
        from world.societies.houses.models import Domain

        domain = Domain.objects.create(
            area=AreaFactory(), name="ProvDomain2", owner_org=self.cov.organization, population=100
        )
        FoodStockpile.objects.create(domain=domain, stored=100)

        rise_battle_covenant_via_session(session=self._rise_session())
        self.cov.refresh_from_db()
        assert self.cov.provisioning_ratio is not None

        stand_down_battle_covenant(covenant=self.cov)
        self.cov.refresh_from_db()
        assert self.cov.provisioning_ratio is None
