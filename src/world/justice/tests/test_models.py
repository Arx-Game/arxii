"""Model + constants tests for the justice app (#1765)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.justice.constants import HeatTier, tier_for_value
from world.justice.factories import AreaLawFactory, CrimeKindFactory, PersonaHeatFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


class TierLadderTest(TestCase):
    def test_tier_boundaries(self):
        self.assertEqual(tier_for_value(0), HeatTier.SAFE)
        self.assertEqual(tier_for_value(1), HeatTier.WATCHED)
        self.assertEqual(tier_for_value(24), HeatTier.WATCHED)
        self.assertEqual(tier_for_value(25), HeatTier.HUNTED)
        self.assertEqual(tier_for_value(60), HeatTier.HEAT_IS_ON)
        self.assertEqual(tier_for_value(99), HeatTier.HEAT_IS_ON)
        self.assertEqual(tier_for_value(100), HeatTier.EXTREME_HEAT)
        self.assertEqual(tier_for_value(100_000), HeatTier.EXTREME_HEAT)


class PersonaHeatModelTest(TestCase):
    def test_temporary_persona_can_hold_heat(self):
        """Decision 1 (#1765): masks soak heat — no established-or-primary guard.

        Deliberate divergence from SocietyReputation.clean(); this test pins it
        so a future 'consistency' pass doesn't re-add the guard.
        """
        mask = PersonaFactory(persona_type=PersonaType.TEMPORARY)
        row = PersonaHeatFactory(persona=mask, value=50)
        row.full_clean()  # must not raise
        self.assertEqual(row.persona.persona_type, PersonaType.TEMPORARY)

    def test_unique_warrant_row(self):
        row = PersonaHeatFactory(value=1)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            PersonaHeatFactory(persona=row.persona, area=row.area, society=row.society)


class AreaLawModelTest(TestCase):
    def test_unique_area_crime_pair(self):
        law = AreaLawFactory()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            AreaLawFactory(area=law.area, crime_kind=law.crime_kind)

    def test_crime_kind_str(self):
        kind = CrimeKindFactory(slug="theft", name="Theft")
        self.assertEqual(str(kind), "Theft")
