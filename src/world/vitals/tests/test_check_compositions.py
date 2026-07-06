"""Resist-check compositions seed the named stat (#1706).

The four resist-style checks previously rolled with zero CheckTypeTrait rows
(a coin-flip on trait_points=0). This suite asserts each now carries its
intended single-stat leg (tenet-permitted for resist checks).
"""

from django.test import TestCase

from world.areas.positioning.constants import CATCH_CHECK_TYPE_NAME


class ResistCheckCompositionTests(TestCase):
    def test_endurance_has_stamina_trait(self):
        from world.vitals.services import _ensure_endurance_check_type

        ct = _ensure_endurance_check_type()
        trait = ct.traits.get().trait  # type: ignore[attr-defined]
        self.assertEqual(trait.name, "stamina")

    def test_mortal_resolve_has_willpower_trait(self):
        from world.vitals.services import _ensure_death_check_type

        ct = _ensure_death_check_type()
        trait = ct.traits.get().trait  # type: ignore[attr-defined]
        self.assertEqual(trait.name, "willpower")

    def test_reflexes_has_wits_trait(self):
        from world.areas.positioning.plummet_content import ensure_catch_content
        from world.checks.models import CheckType

        ensure_catch_content()
        ct = CheckType.objects.get(name=CATCH_CHECK_TYPE_NAME)
        trait = ct.traits.get().trait  # type: ignore[attr-defined]
        self.assertEqual(trait.name, "wits")

    def test_escalation_pace_has_wits_trait(self):
        from world.checks.models import CheckType
        from world.combat.factories import EscalationCurveFactory

        # EscalationCurveFactory.pace_check_type lazy_attribute seeds on access.
        f = EscalationCurveFactory()
        _ = f.pace_check_type  # triggers the lazy_attribute
        ct = CheckType.objects.get(name="Escalation Pace")
        trait = ct.traits.get().trait  # type: ignore[attr-defined]
        self.assertEqual(trait.name, "wits")
