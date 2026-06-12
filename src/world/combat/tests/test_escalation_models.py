from django.test import TestCase

from world.combat.factories import EscalationCurveFactory
from world.combat.models import CombatEncounter


class EscalationCurveModelTests(TestCase):
    def test_curve_defaults(self):
        curve = EscalationCurveFactory()
        self.assertGreaterEqual(curve.start_round, 2)
        self.assertGreater(curve.intensity_step, 0)
        self.assertEqual(curve.max_escalation_level, 0)  # 0 = uncapped

    def test_encounter_escalation_curve_default_null(self):
        encounter = CombatEncounter.objects.create()
        self.assertIsNone(encounter.escalation_curve)

    def test_curve_protected_while_referenced(self):
        from django.db.models import ProtectedError

        curve = EscalationCurveFactory()
        CombatEncounter.objects.create(escalation_curve=curve)
        with self.assertRaises(ProtectedError):
            curve.delete()
