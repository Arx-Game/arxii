"""Tests for the wound-condition wiring + double-bounded HP mend (#2644).

Covers the audit's central gap (the wound pool now actually applies
conditions, not just narrative labels) and the mend_wound() service's
attrition invariant (ADR-0155): the never-to-full fraction cap.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionTemplate
from world.conditions.services import get_active_conditions
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import WOUND_CRIPPLING_NAME
from world.vitals.exceptions import NotAWoundError
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import WoundDetails
from world.vitals.seeds import seed_survivability_content
from world.vitals.services import mend_wound, process_damage_consequences


class WoundPoolAppliesConditionTests(TestCase):
    """The audit's central gap: the wound pool now applies real conditions."""

    def test_failure_tier_applies_crippling_wound_with_wound_details(self) -> None:
        seed_survivability_content()
        # health=40% keeps knockout (>20%) and death (>0%) tiers at difficulty 0 —
        # only the wound tier's perform_check fires, so force_check_outcome's
        # single-shot override lands on the right call.
        vitals = CharacterVitalsFactory(health=40, max_health=100)
        character = vitals.character_sheet.character

        # Must be the SAME CheckOutcome row the seeded pool's consequences are
        # tier-matched against (select_consequence compares outcome_tier by
        # instance equality, not by success_level) — CheckOutcomeFactory's
        # django_get_or_create=("name",) returns the existing "Failure" row
        # ensure_default_wound_pool already created.
        failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        with force_check_outcome(failure_outcome):
            result = process_damage_consequences(
                character_sheet=vitals.character_sheet,
                damage_dealt=60,
                damage_type=None,
            )

        self.assertTrue(result.wounds_applied)
        crippling = ConditionTemplate.objects.get(name=WOUND_CRIPPLING_NAME)
        instance = get_active_conditions(character, condition=crippling).first()
        self.assertIsNotNone(instance)
        details = WoundDetails.objects.get(condition_instance=instance)
        self.assertEqual(details.damage_taken, 60)
        self.assertEqual(details.health_mended_total, 0)


class MendWoundTests(TestCase):
    """mend_wound()'s double-bounded attrition invariant (fraction-cap bound)."""

    def _wound(
        self, *, health: int = 20, max_health: int = 100, damage_taken: int = 100
    ) -> tuple[object, object]:
        vitals = CharacterVitalsFactory(health=health, max_health=max_health)
        instance = ConditionInstanceFactory(target=vitals.character_sheet.character)
        WoundDetails.objects.create(condition_instance=instance, damage_taken=damage_taken)
        return vitals, instance

    def test_mend_caps_at_fraction_of_damage_taken(self) -> None:
        vitals, instance = self._wound(damage_taken=100)
        healer_sheet = CharacterSheetFactory()

        mended = mend_wound(healer_sheet, vitals.character_sheet, instance, amount=200)

        # cap = floor(0.75 * 100) = 75
        self.assertEqual(mended, 75)
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 95)
        details = WoundDetails.objects.get(condition_instance=instance)
        self.assertEqual(details.health_mended_total, 75)

    def test_mend_across_multiple_healers_still_caps(self) -> None:
        vitals, instance = self._wound(health=10, max_health=200, damage_taken=100)
        healer_one = CharacterSheetFactory()
        healer_two = CharacterSheetFactory()

        first = mend_wound(healer_one, vitals.character_sheet, instance, amount=50)
        second = mend_wound(healer_two, vitals.character_sheet, instance, amount=50)

        self.assertEqual(first, 50)
        self.assertEqual(second, 25)  # cap is 75 total, 50 already spent
        details = WoundDetails.objects.get(condition_instance=instance)
        self.assertEqual(details.health_mended_total, 75)

        # A third healer's attempt mends 0 — the wound's cap is exhausted.
        healer_three = CharacterSheetFactory()
        third = mend_wound(healer_three, vitals.character_sheet, instance, amount=50)
        self.assertEqual(third, 0)

    def test_mend_never_exceeds_max_health(self) -> None:
        vitals, instance = self._wound(health=99, max_health=100, damage_taken=100)
        healer_sheet = CharacterSheetFactory()

        mended = mend_wound(healer_sheet, vitals.character_sheet, instance, amount=50)

        self.assertEqual(mended, 1)
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 100)

    def test_mend_on_non_wound_condition_raises(self) -> None:
        vitals = CharacterVitalsFactory(health=50, max_health=100)
        plain_instance = ConditionInstanceFactory(
            target=vitals.character_sheet.character,
            condition=ConditionTemplateFactory(),
        )
        healer_sheet = CharacterSheetFactory()

        with self.assertRaises(NotAWoundError):
            mend_wound(healer_sheet, vitals.character_sheet, plain_instance, amount=10)
