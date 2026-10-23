"""Tests for the wound-condition wiring + double-bounded HP mend (#2644).

Covers the audit's central gap (the wound pool now actually applies
conditions, not just narrative labels) and the mend_wound() service's
attrition invariant (ADR-0156): the never-to-full fraction cap.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionTemplate
from world.conditions.services import get_active_conditions
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import (
    FIRST_AID_MEND_FRACTION,
    NEVER_TO_FULL_FRACTION,
    WOUND_CRIPPLING_NAME,
)
from world.vitals.exceptions import NotAWoundError
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import WoundDetails
from world.vitals.seeds import seed_survivability_content
from world.vitals.services import mend_wound, process_damage_consequences


@override_settings(SEED_SAMPLE_CONTENT=True)
class WoundPoolAppliesConditionTests(TestCase):
    """The audit's central gap: the wound pool now applies real conditions.

    Gates on SEED_SAMPLE_CONTENT (#2698) — ``seed_survivability_content``
    drives the real Crippling Wound condition through the wound pool.
    """

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


class MendWoundFractionTests(TestCase):
    """Each mend brings its own fraction; the wound never passes the highest one used (#4600).

    A 20-damage wound throughout: a 0.40 mend may restore 8, a 0.70 mend 14.
    """

    def _wound(self, *, damage_taken: int = 20) -> tuple[object, object]:
        vitals = CharacterVitalsFactory(health=10, max_health=100)
        instance = ConditionInstanceFactory(target=vitals.character_sheet.character)
        WoundDetails.objects.create(condition_instance=instance, damage_taken=damage_taken)
        return vitals, instance

    def _mend(self, vitals: object, instance: object, fraction: Decimal | None) -> int:
        return mend_wound(
            CharacterSheetFactory(),
            vitals.character_sheet,  # type: ignore[attr-defined]
            instance,  # type: ignore[arg-type]
            amount=50,
            cap_fraction=fraction,
        )

    def test_low_then_high_totals_the_high_fraction(self) -> None:
        vitals, instance = self._wound()

        self.assertEqual(self._mend(vitals, instance, Decimal("0.40")), 8)
        self.assertEqual(self._mend(vitals, instance, Decimal("0.70")), 6)
        self.assertEqual(self._mend(vitals, instance, Decimal("0.40")), 0)

        details = WoundDetails.objects.get(condition_instance=instance)
        self.assertEqual(details.health_mended_total, 14)

    def test_high_then_low_never_passes_the_high_fraction(self) -> None:
        vitals, instance = self._wound()

        self.assertEqual(self._mend(vitals, instance, Decimal("0.70")), 14)
        self.assertEqual(self._mend(vitals, instance, Decimal("0.40")), 0)

        details = WoundDetails.objects.get(condition_instance=instance)
        self.assertEqual(details.health_mended_total, 14)

    def test_a_fraction_above_the_ceiling_stops_at_the_ceiling(self) -> None:
        vitals, instance = self._wound()

        # 0.95 is above the 0.75 ceiling: int(0.75 x 20) = 15.
        self.assertEqual(self._mend(vitals, instance, Decimal("0.95")), 15)

    def test_no_fraction_means_the_ceiling(self) -> None:
        vitals, instance = self._wound()

        self.assertEqual(self._mend(vitals, instance, None), 15)

    def test_a_zero_fraction_mends_nothing_rather_than_meaning_the_ceiling(self) -> None:
        vitals, instance = self._wound()

        self.assertEqual(self._mend(vitals, instance, Decimal("0.00")), 0)

    def test_first_aid_stops_at_its_own_fraction(self) -> None:
        vitals, instance = self._wound()

        self.assertEqual(FIRST_AID_MEND_FRACTION, Decimal("0.50"))
        self.assertLess(FIRST_AID_MEND_FRACTION, NEVER_TO_FULL_FRACTION)
        self.assertEqual(self._mend(vitals, instance, FIRST_AID_MEND_FRACTION), 10)
        # A healing technique at the ceiling still finds room above first aid.
        self.assertEqual(self._mend(vitals, instance, NEVER_TO_FULL_FRACTION), 5)
